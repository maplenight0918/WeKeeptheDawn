if __package__:
    from . import _bootstrap
else:
    import _bootstrap
import argparse
import hashlib
import json
import re
from pathlib import Path
from pypdf import PdfReader
from app.world_rules import ROOT, digest

PREPROCESSING_VERSION='original-paragraphs-v1'

def split_text(text, target=450, overlap=75):
    # Preserve paragraph/table line breaks; split only oversized paragraphs by words.
    paragraphs=re.split(r'\n\s*\n',text.strip())
    current=[]; count=0
    for paragraph in paragraphs:
        words=paragraph.split()
        if len(words)>600:
            if current:
                yield '\n\n'.join(current); current=[]; count=0
            for start in range(0,len(words),target-overlap):
                yield ' '.join(words[start:start+target])
            continue
        if current and count+len(words)>600:
            joined='\n\n'.join(current)
            yield joined
            current=[' '.join(joined.split()[-overlap:])]; count=overlap
        current.append(paragraph); count+=len(words)
        if count>=target:
            joined='\n\n'.join(current); yield joined
            current=[' '.join(joined.split()[-overlap:])]; count=overlap
    if current and count>overlap: yield '\n\n'.join(current)

def prepare():
    manifest=ROOT/'data/source_manifest.jsonl'
    if not manifest.exists():
        print('Missing source_manifest.jsonl; run scripts/acquire_sources.py first.'); return 2
    records=[json.loads(line) for line in manifest.read_text(encoding='utf-8').splitlines() if line]
    chunks=[]; missing=[]
    for record in records:
        path=ROOT/record['local_path']
        if record['access_status']!='full_text_acquired' or not path.exists(): missing.append(record['document_id']); continue
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
            missing.append(record['document_id']+':hash_mismatch'); continue
        if path.suffix.lower()=='.pdf':
            reader=PdfReader(path); pages=record.get('pages') or list(range(1,len(reader.pages)+1))
            texts=[(page,reader.pages[page-1].extract_text(extraction_mode='layout')) for page in pages if page<=len(reader.pages)]
        elif path.suffix.lower() in {'.txt','.md'}:
            texts=[(None,path.read_text(encoding='utf-8'))]
        else: missing.append(record['document_id']+':unsupported_format'); continue
        processed=[]
        for page,text in texts:
            if not text or len(text.split())<25: continue
            text=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',text)
            processed.append({'pdf_page':page,'text':text})
            for index,body in enumerate(split_text(text)):
                text_hash=hashlib.sha256(body.encode()).hexdigest()
                chunk_id=record['document_id']+'-p'+str(page)+'-'+str(index)+'-'+text_hash[:10]
                chunks.append({'document_id':record['document_id'],'chunk_id':chunk_id,'text':body,'title':record['title'],'source_url':record['url'],
                               'pdf_page':page,'printed_page':None,'section':'original page; printed page not transcribed',
                               'hash':text_hash,'verification_status':'full_text_acquired_support_not_automatically_verified'})
        (ROOT/'data/processed'/ (record['document_id']+'.json')).write_text(json.dumps(processed,ensure_ascii=False),encoding='utf-8')
    if not chunks:
        print('No readable verified original text; missing: '+','.join(missing)); return 2
    (ROOT/'data/chunks.jsonl').write_text('\n'.join(json.dumps(c,ensure_ascii=False) for c in chunks)+'\n',encoding='utf-8')
    metadata={'corpus_version':'corpus-'+digest([(c['chunk_id'],c['hash']) for c in chunks])[:16],'preprocessing_version':PREPROCESSING_VERSION,
              'documents':len(set(c['document_id'] for c in chunks)),'chunks':len(chunks),'missing':missing,'research_status':'partial'}
    (ROOT/'data/corpus_metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps(metadata)); return 2 if missing else 0

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--local',action='store_true'); parser.parse_args()
    raise SystemExit(prepare())
