"""Three exact2026 force boxes and five named/graded skill items."""
import hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data,CLIENT_SHA
SHA='116d955c9ba759fb59a6946a83b2f56a3f413913af4e7e3c61bbb8ce8d6cf417'
BOXES=frozenset((723616,720746,723617));_boxes={};_items={}
def register():
 global _boxes,_items
 p=Path(__file__).resolve().parents[1]/'data/boosting2026-force-support.json';raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('Selected force support identity')
 d=json.loads(raw);c=client_data()
 if d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=c.manifest['catalog_sha256'] or d['grade_enum']!=c.resource('Enum.lua')['ITEM_GRADE']:raise ValueError('Selected force support client/grade identity')
 # Original evidence paths are provenance metadata. The immutable data SHA,
 # finite outputs, and current item records are validated here at runtime.
 boxes={r['template']:r for r in d['boxes']};items={r['template']:r for r in d['items']}
 if set(boxes)!=BOXES or set(items)!={295712,306002,295707,295714,306004}:raise ValueError('Selected force finite definitions')
 expected={723616:(0,[720746,723617]),720746:(1,[295712,306002,295707]),723617:(1,[295714,306004])}
 for t,r in {**items,**boxes}.items():
  item=c.item(t)
  if item['name']!=r['name'] or hashlib.sha256(item['record']).hexdigest()!=r['record_sha256'] or item['item_type']!=7 or item['metadata']!=0 or (r['metadata'],r['group'],r['max_stack'])!=(0,4,999):raise ValueError('Selected force native item')
  if t in items and (item['flags4']>>20)&15!=r['grade']:raise ValueError('Selected force original item grade')
 for t,r in boxes.items():
  rule=r['original_random_rule']['arguments'][-1]
  if (r['selection_count'],[x['template'] for x in r['outputs']])!=expected[t] or [rule[k] for k in ('m_ItemID','m_KeyItemID','m_iGiveCount','m_RequiredKeyCount','m_UseCondition')]!=[t,0,r['selection_count'],0,1] or any(x['quantity']!=1 for x in r['outputs']):raise ValueError('Selected force original choice policy')
 if _boxes and (_boxes!=boxes or _items!=items):raise ValueError('Cannot replace selected force support definitions')
 from els_server.domain.inventory_items import VERIFIED_TEMPLATES as meta,TEMPLATE_BAG_GROUPS as groups,TEMPLATE_MAX_STACKS as stacks
 for t,r in {**items,**boxes}.items():
  if t in meta and (meta[t],groups[t],stacks[t])!=(0,4,999):raise ValueError('Selected force registration conflict')
 for t in {*items,*boxes}:meta[t]=0;groups[t]=4;stacks[t]=999
 _boxes,_items=boxes,items
 from els_server.domain.cubes import catalog
 catalog.cache_clear()
def boxes():return MappingProxyType(_boxes)
def items():return MappingProxyType(_items)
def entries():return tuple(MappingProxyType(dict(template=t,selection_count=r['selection_count'],entries=tuple(dict(x) for x in r['outputs']),selected_force_support=True)) for t,r in sorted(_boxes.items()))
