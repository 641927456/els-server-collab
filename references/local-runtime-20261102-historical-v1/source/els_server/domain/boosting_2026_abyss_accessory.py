"""One owned 723621 all-output abyss accessory box.

Contents are fixed by the official announcement and the in-game tooltip:
梦烟香炉, 环绕的魔障 and 暗鬼的纹章, one each. The client exposes no original
group-content table for 723621, so the mapping stays explicitly local.
"""
import functools,hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data,CLIENT_SHA

BOX=723621
OUTPUTS=(30675,30676,30677)
SHA='d939e251102dc0ccd5a742df83ba24ed592b0b938195205637d43f7e0fd2719f'
PROVENANCE='官网《艾尔之光》战斗力助力活动公告所列内含（梦烟香炉*1、环绕的魔障*1、暗鬼的纹章*1），与游戏内悬浮说明一致'


@functools.lru_cache(maxsize=1)
def definition():
 p=Path(__file__).resolve().parents[1]/'data/boosting2026-abyss-accessory-support.json';raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('Selected abyss accessory identity')
 d=json.loads(raw);c=client_data()
 if (d['schema_version'],d['client_sha256'],d['catalog_sha256'])!=(1,CLIENT_SHA,c.manifest['catalog_sha256']):raise ValueError('Selected abyss accessory client identity')
 if d['original_group_contents_missing'] is not True or d['local_ID_mapping_not_retail_group_claim'] is not True:raise ValueError('Selected abyss accessory provenance flags')
 if d['provenance']!=PROVENANCE:raise ValueError('Selected abyss accessory provenance')
 boxes=d['boxes']
 if len(boxes)!=1:raise ValueError('Selected abyss accessory finite scope')
 box=boxes[0]
 item=c.item(BOX)
 if (box['template'],box['name'],box['item_type'],box['metadata'],box['group'],box['max_stack'],box['selection_count'])!=(BOX,item['name'],7,0,4,999,0):raise ValueError('Selected abyss accessory original box')
 if (item['item_type']!=7 or item['metadata']!=0 or hashlib.sha256(item['record']).hexdigest()!=box['record_sha256']):raise ValueError('Selected abyss accessory native box record')
 entries=box['entries']
 if [r['template'] for r in entries]!=list(OUTPUTS):raise ValueError('Selected abyss accessory finite outputs')
 for r in entries:
  piece=c.item(r['template'])
  if (piece['name'],piece['item_type'],piece['metadata'],r['quantity'],r['group'],r['max_stack'],piece['equip_position'])!=(r['name'],3,0,1,2,1,r['equip_position']):raise ValueError('Selected abyss accessory native piece')
  if hashlib.sha256(piece['record']).hexdigest()!=r['record_sha256']:raise ValueError('Selected abyss accessory piece record')
 return MappingProxyType(dict(box=MappingProxyType(box),entries=tuple(MappingProxyType(r) for r in entries)))
def enabled():return True

def entry():
 d=definition()
 return MappingProxyType(dict(template=BOX,name=d['box']['name'],mode='fixed',selection_count=0,
  entries=tuple(dict(template=r['template'],quantity=r['quantity'],name=r['name']) for r in d['entries']),
  abyss_accessory_support=True))

def validate_box_grants(plan):
 # This finite context is supplied only by the owned-box transaction, never by
 # generic drops, shops or client data: accessories stay acquisition-restricted.
 d=definition()
 if not isinstance(plan,list) or len(plan)!=len(d['entries']):raise ValueError('Selected abyss accessory grant source')
 if [p.get('template') for p in plan]!=list(OUTPUTS):raise ValueError('Selected abyss accessory exact box outputs')
 for p,r in zip(plan,d['entries']):
  if (p.get('metadata'),p.get('group'),p.get('quantity'))!=(r['metadata'],r['group'],r['quantity']):raise ValueError('Selected abyss accessory grant identity')
  if set(p)!={'template','metadata','group','quantity'}:raise ValueError('Selected abyss accessory grant instance fields')
 return True
