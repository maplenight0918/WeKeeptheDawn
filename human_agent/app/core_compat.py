"""Compatibility helpers for supplied Core schemas and explicit candidate data."""
import json
from pydantic import ValidationError
from app.schemas import Plan

ANNOTATIONS={'title','description','$comment','examples','default','$schema','$id'}

def normalize_schema(schema,root=None,refs=()):
    root=schema if root is None else root
    if isinstance(schema,list): return [normalize_schema(v,root,refs) for v in schema]
    if not isinstance(schema,dict): return schema
    if '$ref' in schema:
        ref=schema['$ref']
        if not isinstance(ref,str) or not ref.startswith('#/') or ref in refs or len(refs)>30:
            raise ValueError('Only acyclic local schema references are supported')
        target=root
        for part in ref[2:].split('/'):
            target=target[part.replace('~1','/').replace('~0','~')]
        result=normalize_schema(target,root,refs+(ref,))
        siblings=normalize_schema({k:v for k,v in schema.items() if k!='$ref'},root,refs)
        if any(k in result and result[k]!=v for k,v in siblings.items()):
            raise ValueError('Conflicting schema reference siblings')
        return {**result,**siblings}
    out={}
    for key,value in schema.items():
        if key in ANNOTATIONS or key in {'$defs','definitions'}: continue
        if key in {'properties','patternProperties'}:
            out[key]={k:normalize_schema(v,root,refs) for k,v in value.items()}
        elif key in {'required','enum','type'} and isinstance(value,list):
            out[key]=sorted(value,key=lambda x:json.dumps(x,sort_keys=True))
        else: out[key]=normalize_schema(value,root,refs)
    return out

def compatible_schema(actual,expected):
    try: return normalize_schema(actual)==normalize_schema(expected)
    except (KeyError,TypeError,AttributeError,ValueError,RecursionError): return False

def read_core_plan(world,content):
    """Use only a complete, explicitly supplied next-tick plan; never promote chat history."""
    if world.next_tick_plan is not None: return world.next_tick_plan,[],None
    choices=[v for v in [world.current_plan,content.current_plan] if v is not None]
    if not choices: return None,[],None
    if len(choices)>1 and choices[0]!=choices[1]:
        return None,['world 與 content 的 current_plan 不一致；不選擇其中一份作核算基準。'],choices
    raw=choices[0]
    try:
        # Some Core messages wrap an explicit candidate in candidate_plan.
        candidate=raw.get('candidate_plan',raw)
        plan=Plan.model_validate(candidate)
        if plan.for_tick!=world.tick+1:
            return None,['current_plan 不是此次 world 的下一 tick；保留為討論資料，不套入核算。'],raw
        if {t.crew_id for t in plan.crew_tasks}!={c.id for c in world.crew}:
            raise ValueError('Unknown crew in Core plan')
        plot_ids={p.id for p in world.plots}
        if any(t.plot_id not in plot_ids for t in plan.crew_tasks if hasattr(t,'plot_id')) or any(a.plot_id not in plot_ids for a in plan.irrigation_allocations or []):
            raise ValueError('Unknown plot in Core plan')
        return plan,[],raw
    except (ValidationError,ValueError,TypeError,AttributeError):
        return None,['current_plan 缺少可辨識的完整任務、順序或配額；可討論內容，但不宣稱已核算。'],raw
