if __package__:
    from . import _bootstrap
else:
    import _bootstrap
import argparse
import asyncio
import json
import os
import uuid
import numpy as np
from app.world_rules import ROOT, digest
from app.settings import Settings, ConfigurationError
from app.providers import EmbeddingClient, Deadline, ProviderError

def atomic_json(path,value):
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(temp,path)

async def build(settings,mode,offline=False):
    try:
        chunks=[json.loads(x) for x in (ROOT/'data/chunks.jsonl').read_text(encoding='utf-8').splitlines() if x]
        corpus=json.loads((ROOT/'data/corpus_metadata.json').read_text())
        if not chunks or corpus['corpus_version']!='corpus-'+digest([(c['chunk_id'],c['hash']) for c in chunks])[:16]: raise ValueError()
        import hashlib
        if any(hashlib.sha256(c['text'].encode()).hexdigest()!=c['hash'] for c in chunks): raise ValueError()
    except (OSError,ValueError,KeyError):
        print('Missing/invalid corpus; run prepare_corpus.py --local.'); return 2
    index=settings.path(settings.index_dir); index.mkdir(parents=True,exist_ok=True)
    ids=[c['chunk_id'] for c in chunks]
    if mode in {'bm25','both'}:
        atomic_json(index/'bm25_metadata.json',{'corpus_version':corpus['corpus_version'],'chunk_ids':ids,'tokenizer':'lexical-en-zh-v1'})
        print('BM25 ready: '+str(len(chunks))+' chunks',flush=True)
    if mode=='bm25': return 0
    embed=EmbeddingClient(settings); cache=ROOT/'data/embedding_cache'; cache.mkdir(parents=True,exist_ok=True)
    vectors={}; missing=[]
    for c in chunks:
        key=embed.cache_key(c['text']); path=cache/(key+'.npy')
        try: vectors[c['chunk_id']]=embed.validate_vectors(np.load(path,allow_pickle=False),1)[0]
        except (OSError,ValueError,ProviderError): missing.append(c)
    if missing and (offline or not settings.embedding_api_key):
        print('Dense incomplete: '+str(len(missing))+' uncached chunks; '+('offline cannot generate Voyage vectors' if offline else 'missing EMBEDDING_API_KEY')); return 2
    try:
        # Sequential bounded batches; individual texts <= 600 words and conservative total byte budget.
        while missing:
            batch=[]; size=0
            while missing and len(batch)<settings.embedding_batch_size:
                candidate=missing[0]
                if batch and size+len(candidate['text'].encode())>24000: break
                batch.append(missing.pop(0)); size+=len(candidate['text'].encode())
            array=await embed.embed_documents([c['text'] for c in batch],Deadline(settings.embedding_timeout_seconds*3))
            for c,vector in zip(batch,array):
                vectors[c['chunk_id']]=vector
                path=cache/(embed.cache_key(c['text'])+'.npy'); temp=path.with_suffix('.tmp')
                with temp.open('wb') as stream: np.save(stream,vector[None,:],allow_pickle=False)
                os.replace(temp,path)
            print('Dense cached '+str(len(vectors))+'/'+str(len(chunks)),flush=True)
    except ProviderError as e:
        print('Dense incomplete: '+str(e)); return 2
    array=np.asarray([vectors[cid] for cid in ids],dtype=np.float32)
    version='index-'+digest({'identity':embed.identity,'corpus':corpus['corpus_version']})[:16]
    # Immutable generation plus atomic pointer publishes all three artifacts together.
    name=version+'-'+uuid.uuid4().hex[:8]; directory=index/'generations'/name; directory.mkdir(parents=True)
    np.save(directory/'vectors.npy',array,allow_pickle=False)
    atomic_json(directory/'chunk_ids.json',ids)
    atomic_json(directory/'index_metadata.json',{'index_version':version,'corpus_version':corpus['corpus_version'],
                'identity':embed.identity,'chunk_ids':ids,'vectors_hash':digest(array.tolist()),'normalization':'L2 float32 cosine dot'})
    atomic_json(index/'current.json',{'generation':name})
    print('Dense ready: '+version+'; embedding_batches='+str(embed.calls)); return 0

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--mode',choices=['dense','bm25','both'],required=True); p.add_argument('--offline',action='store_true'); args=p.parse_args()
    try: code=asyncio.run(build(Settings.load(),args.mode,args.offline))
    except ConfigurationError as e: print(str(e)); code=2
    raise SystemExit(code)
