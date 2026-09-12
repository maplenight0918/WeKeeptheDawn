"""Explicit network acquisition. Never called at API startup."""
if __package__:
    from . import _bootstrap
else:
    import _bootstrap
import asyncio
import hashlib
import json
from pathlib import Path
import httpx
from app.world_rules import ROOT

SOURCES = [
    dict(document_id='bvad_2022',title='Life Support Baseline Values and Assumptions Document, Rev 2',authors=['Michael K. Ewert','Thomas T. Chen','C. D. Powell'],year='2022',url='https://ntrs.nasa.gov/api/citations/20210024855/downloads/BVAD_2.15.22-final.pdf',topics=['energy','water','oxygen','activity'],pages=list(range(68,78))),
    dict(document_id='metabolic_2019',title='Astronaut Mass Balance for Long Duration Missions',authors=['Michael K. Ewert','Chel Stromgren'],year='2019',url='https://ntrs.nasa.gov/api/citations/20190027563/downloads/20190027563.pdf',topics=['metabolic','water','oxygen','activity'],pages=None),
    dict(document_id='nutrition_requirements',title='Nutrition Requirements, Standards, and Operating Bands for Exploration Missions',authors=['NASA Johnson Space Center Nutritional Biochemistry Laboratory'],year='2005 revision 1',url='https://ntrs.nasa.gov/api/citations/20200001703/downloads/20200001703.pdf',topics=['nutrition','energy','requirements'],pages=None),
    dict(document_id='human_adaptation_2021',title='Human Adaptation to Spaceflight: The Role of Food and Nutrition, Second Edition',authors=['Scott M. Smith','Sara R. Zwart','Grace L. Douglas','Martina Heer'],year='2021',url='https://www.nasa.gov/sites/default/files/atoms/files/human_adaptation_2021_final.pdf',topics=['nutrition','energy','water'],pages=list(range(1,16))+list(range(35,51))),
    dict(document_id='hidh_rev1',title='Human Integration Design Handbook, Revision 1',authors=['NASA'],year='2014',url='https://www.nasa.gov/wp-content/uploads/2023/03/human-integration-design-handbook-revision-1.pdf',topics=['water','activity','human requirements'],pages=None)
]

async def main():
    records=[]
    async with httpx.AsyncClient(timeout=55,follow_redirects=True) as client:
        for source in SOURCES:
            path=ROOT/'data/raw'/ (source['document_id']+'.pdf')
            record={**source,'local_path':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':None,'access_status':'unavailable','exclusion_reason':None}
            try:
                if not path.exists():
                    response=await client.get(source['url']); response.raise_for_status()
                    if not response.content.startswith(b'%PDF'): raise ValueError('not_pdf')
                    path.write_bytes(response.content)
                from pypdf import PdfReader
                reader=PdfReader(path)
                record['page_count']=len(reader.pages)
                record['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
                record['access_status']='full_text_acquired'
                if source['document_id']=='hidh_rev1':
                    # Explicitly index nutrition/water/activity pages plus neighbors, not every engineering discipline.
                    selected=set()
                    for i,page in enumerate(reader.pages):
                        text=(page.extract_text() or '').lower()
                        if any(term in text for term in ['potable water','metabolic rate','energy requirements','food and nutrition']):
                            selected.update(range(max(1,i),min(len(reader.pages),i+2)+1))
                    record['pages']=sorted(selected)
                print(source['document_id']+': acquired '+str(len(reader.pages))+' pages',flush=True)
            except Exception as e:
                record['exclusion_reason']=type(e).__name__
                print(source['document_id']+': unavailable ('+type(e).__name__+')',flush=True)
            records.append(record)
            (ROOT/'data/source_manifest.jsonl').write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in records)+'\n',encoding='utf-8')
    return 0 if all(x['access_status']=='full_text_acquired' for x in records) else 2

if __name__=='__main__':
    raise SystemExit(asyncio.run(main()))
