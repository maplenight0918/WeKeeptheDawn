import json
import re
from pathlib import Path
import numpy as np
from rank_bm25 import BM25Okapi
from app.world_rules import ROOT, digest, get_world_rule
from app.providers import EmbeddingClient, ProviderError
from app.evidence_review import reviewed_claims

def tokens(text):
    terms=re.findall(r'[a-z0-9]+(?:\.[0-9]+)?',text.lower())
    stop={'a','an','the','of','and','or','to','in','for','is','are','what','how','does','do','with','from','per','on','as','at','be','by','that','this','it','not','can'}
    terms=[t for t in terms if t not in stop]
    # Small explicit lexical translation improves Chinese BM25 without changing source text.
    translations={'飲水':'potable drinking water','水分':'potable water','用水':'water consumption','氧氣':'oxygen consumed','耗氧':'oxygen metabolic','能量':'energy food calories','熱量':'energy food calories','活動':'exercise activity metabolic','營養':'nutrition nutrients','喝水':'drinking potable water','太空人':'crewmember astronaut'}
    for word,english in translations.items():
        if word in text: terms.extend(english.split())
    return terms

def world_route(query):
    q=query.lower()
    if ('製水' in q or 'water production' in q) and any(w in q for w in ['物理','守恆','physical','conservation','遊戲','game']):
        return ['water_production.conversion']
    if any(w in q for w in ['歸零','歸0','zero','死亡']) and any(w in q for w in ['個人','personal','能量','energy']):
        return ['crew.personal.death']
    return []

class Retriever:
    def __init__(self,settings,embedding=None):
        self.settings=settings; self.embedding=embedding or EmbeddingClient(settings)
        self.chunks=[]; self.metadata={}; self.index_metadata={}; self.vectors=None; self.bm25=None; self.dense_error=None
        try:
            self.metadata=json.loads((ROOT/'data/corpus_metadata.json').read_text(encoding='utf-8'))
            self.chunks=[json.loads(line) for line in (ROOT/'data/chunks.jsonl').read_text(encoding='utf-8').splitlines() if line]
            expected='corpus-'+digest([(c['chunk_id'],c['hash']) for c in self.chunks])[:16]
            import hashlib
            if expected!=self.metadata['corpus_version'] or any(hashlib.sha256(c['text'].encode()).hexdigest()!=c['hash'] for c in self.chunks):
                raise ValueError('corpus_hash_mismatch')
        except (OSError,ValueError,KeyError):
            self.chunks=[]; self.metadata={}; self.dense_error='corpus_missing_or_invalid'
        index=settings.path(settings.index_dir)
        try:
            bm=json.loads((index/'bm25_metadata.json').read_text(encoding='utf-8'))
            if bm['corpus_version']!=self.metadata.get('corpus_version') or bm['chunk_ids']!=[c['chunk_id'] for c in self.chunks]: raise ValueError()
            self.bm25=BM25Okapi([tokens(c['text']) for c in self.chunks]) if self.chunks else None
        except (OSError,ValueError,KeyError): pass
        try:
            pointer=json.loads((index/'current.json').read_text())
            generation=index/'generations'/pointer['generation']
            if generation.resolve().parent!=(index/'generations').resolve(): raise ValueError()
            meta=json.loads((generation/'index_metadata.json').read_text())
            ids=json.loads((generation/'chunk_ids.json').read_text())
            if meta['identity']!=self.embedding.identity or meta['corpus_version']!=self.metadata.get('corpus_version') or ids!=[c['chunk_id'] for c in self.chunks] or meta['chunk_ids']!=ids:
                raise ValueError('incompatible_index')
            vectors=np.load(generation/'vectors.npy',allow_pickle=False)
            if digest(vectors.tolist())!=meta['vectors_hash']: raise ValueError('vectors_hash_mismatch')
            self.vectors=self.embedding.validate_vectors(vectors,len(ids)); self.index_metadata=meta
        except (OSError,ValueError,KeyError,ProviderError):
            self.dense_error=self.dense_error or 'dense_missing_stale_or_incompatible'
        self.chunk_tokens=[set(tokens(c['text'])) for c in self.chunks]
        self.vocabulary=set().union(*self.chunk_tokens) if self.chunk_tokens else set()

    def info(self,mode='not_used',reason=None):
        return {'requested_mode':self.settings.retrieval_mode,'actual_mode':mode,'fallback_reason':reason,
                'model':self.settings.embedding_model if mode in {'dense','mixed'} else None,
                'dimensions':self.settings.embedding_dimensions if mode in {'dense','mixed'} else None,
                'ranking_method':{'dense':'cosine','mixed':'rrf_with_numeric_anchors','bm25':'bm25'}.get(mode,'none')}

    async def retrieve(self,query,top_k,deadline,offline=False):
        rules=world_route(query)
        if rules: return get_world_rule(rules),self.info('not_used','world_rule_routing')
        top_k=max(1,min(int(top_k),10))
        mode='none'; reason=None; scores=None
        if self.settings.retrieval_mode=='dense' and not offline:
            if self.vectors is not None:
                try:
                    vector=await self.embedding.embed_query(query,deadline)
                    scores=self.vectors@vector; mode='dense'
                except ProviderError as e: reason=str(e)
            else: reason=self.dense_error
        elif offline and self.settings.retrieval_mode=='dense': reason='mock_offline_bm25'
        if scores is None and (self.settings.retrieval_mode=='bm25' or self.settings.retrieval_fallback=='bm25' or offline):
            if self.bm25 is not None:
                scores=self.bm25.get_scores(tokens(query)); mode='bm25'
            else: reason=(reason+'; ' if reason else '')+'bm25_missing_or_stale'
        if scores is None: return [],self.info('none',reason)
        # Zero lexical overlap is insufficient support even if dense returns positive similarity.
        # This is conservative; source existence and semantic support remain separate.
        query_terms=set(tokens(query))
        if not query_terms & self.vocabulary:
            return [],self.info(mode,reason)
        indices=np.argsort(-scores,kind='stable')[:top_k]
        if mode=='dense' and self.bm25 is not None and self.settings.retrieval_fallback=='bm25':
            lexical=self.bm25.get_scores(tokens(query))
            fused=np.zeros(len(self.chunks),dtype=np.float64)
            for ranking in [scores,lexical]:
                order=[int(i) for i in np.argsort(-ranking,kind='stable') if ranking[i]>0][:max(20,top_k*4)]
                for rank,index in enumerate(order,1): fused[index]+=1/(60+rank)
            # Explicit numbers are anchors, not facts inferred from similarity. Require
            # both an exact numeric token and nonnumeric query overlap in the original.
            numbers={t for t in query_terms if re.fullmatch(r'\d+(?:\.\d+)?',t)}
            words=query_terms-numbers
            anchors=[i for i,t in enumerate(self.chunk_tokens) if numbers&t and words&t and lexical[i]>0]
            anchors.sort(key=lambda i:(-len(numbers & self.chunk_tokens[i]),-float(lexical[i]),i))
            order=anchors+[int(i) for i in np.argsort(-fused,kind='stable') if fused[i]>0 and i not in anchors]
            indices=order[:top_k]; scores=fused; mode='mixed'
        evidence=[]
        for i in indices:
            if float(scores[i])<=0 and mode!='mixed': continue
            c=self.chunks[int(i)]
            evidence.append({'id':c['chunk_id'],'type':'scientific_source','title':c['title'],'document_id':c['document_id'],
                             'chunk_id':c['chunk_id'],'rule_id':None,'locator':'PDF physical page '+str(c['pdf_page'])+'; '+c['section'],
                             'source_url':c['source_url'],'excerpt':c['text'],'verification_status':c['verification_status'],
                             'reviewed_claims':reviewed_claims(c['chunk_id'],c['text'])})
        return evidence,self.info(mode,reason)
