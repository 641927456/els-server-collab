"""Two official 2026 change-force select boxes (723687 E / 723688 A).

Both boxes are select cubes: exactly one item from the official announcement
list. The official pages enumerate every entry per class; the client record
carries no job ownership, so the choice set is the published list itself and no
class filter is invented here.
"""
import functools,hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data,CLIENT_SHA

BOXES=(723687,723688)
ANNOUNCEMENTS={723687:'https://els.ztgame.com/html/news/13500bb/002-1754-0197f-892651.shtml',
               723688:'https://els.ztgame.com/html/news/135251e/m_000-1769-019fa-407143.shtml'}
FILES={723687:'boosting2026-change-force-e.json',723688:'boosting2026-change-force-a.json'}
SHAS={723687:'a6a38ed59b08366f8a39723fe0df8a68117b838a1d4a8b8edda651ce143c6a1d',
      723688:'18a879bbf3624e9d40b773cb5cc0dc16edc0396882c32a3dfb3d77be9102086f'}


@functools.lru_cache(maxsize=1)
def definitions():
 c=client_data();result={}
 for t in BOXES:
  p=Path(__file__).resolve().parents[1]/'data'/FILES[t];raw=p.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=SHAS[t]:raise ValueError('Selected change-force identity')
  d=json.loads(raw)
  if (d['schema_version'],d['client_sha256'],d['catalog_sha256'])!=(1,CLIENT_SHA,c.manifest['catalog_sha256']):raise ValueError('Selected change-force client identity')
  if d['original_group_contents_missing'] is not True or d['local_ID_mapping_not_retail_group_claim'] is not True:raise ValueError('Selected change-force provenance flags')
  source=d['official_source']
  if source['announcement']!=ANNOUNCEMENTS[t] or source['unmatched_names']!=[]:raise ValueError('Selected change-force official scope')
  boxes=d['boxes']
  if len(boxes)!=1:raise ValueError('Selected change-force finite scope')
  box=boxes[0];item=c.item(t)
  if (box['template'],box['name'],box['item_type'],box['metadata'],box['group'],box['max_stack'],box['selection_count'])!=(t,item['name'],7,0,4,999,1):raise ValueError('Selected change-force original box')
  if (item['item_type']!=7 or item['metadata']!=0 or hashlib.sha256(item['record']).hexdigest()!=box['record_sha256']):raise ValueError('Selected change-force native box record')
  entries=box['entries']
  if (len(entries)!=source['announcement_item_count'] or len(entries)!=source['catalog_matched_count'] or len({r['template'] for r in entries})!=len(entries)):raise ValueError('Selected change-force coverage')
  for r in entries:
   piece=c.item(r['template'])
   if (piece['name'],piece['item_type'],piece['metadata'],r['quantity'],r['group'],r['max_stack'])!=(r['name'],7,0,1,4,999):raise ValueError('Selected change-force native entry')
   if hashlib.sha256(piece['record']).hexdigest()!=r['record_sha256']:raise ValueError('Selected change-force entry record')
  result[t]=MappingProxyType(dict(box=MappingProxyType(box),entries=tuple(MappingProxyType(r) for r in entries)))
 return MappingProxyType(result)
def enabled():return True

def entries():
 out=[]
 for t in BOXES:
  d=definitions()[t]
  out.append(MappingProxyType(dict(template=t,name=d['box']['name'],metadata=0,group=4,max_stack=999,mode='select',
   selection_count=1,change_force_select=True,
   entries=tuple(dict(template=r['template'],quantity=r['quantity'],name=r['name']) for r in d['entries']))))
 return tuple(out)
