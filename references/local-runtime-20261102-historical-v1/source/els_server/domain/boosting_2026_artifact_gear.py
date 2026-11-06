"""One owned 723618 all-output Master Artifact gear support box.

The client has no original group-content table for this box, so the contents are
declared explicitly from the official announcement: one headpiece, one armor,
one necklace and two rings. No retail drop rate is claimed.
"""
import functools,hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data,CLIENT_SHA

BOX=723618
OUTPUTS=(168600,168601,168602,168603)
QUANTITIES=(1,1,1,2)
SHA='6615113d349a48805f86c6a6b684913fabd92853502cf1f1f9d4a44a94bc6773'


@functools.lru_cache(maxsize=1)
def definition():
 p=Path(__file__).resolve().parents[1]/'data/boosting2026-artifact-gear-support.json';raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('Selected artifact gear support identity')
 d=json.loads(raw);c=client_data()
 if (d['schema_version'],d['client_sha256'],d['catalog_sha256'])!=(1,CLIENT_SHA,c.manifest['catalog_sha256']):raise ValueError('Selected artifact gear support client identity')
 # No original group content exists for723618; the two declarations below keep
 # this explicit local mapping from being read as a retail group claim.
 if d['original_group_contents_missing'] is not True or d['local_ID_mapping_not_retail_group_claim'] is not True:raise ValueError('Selected artifact gear support provenance flags')
 if d['provenance']!='官网《艾尔之光》战斗力助力活动公告所列内含（神物头饰*1、神物甲胄*1、神物项链*1、神物戒指*2），模板号取 artifact_progression.json 官方神物装备集合':raise ValueError('Selected artifact gear support provenance')
 boxes=d['boxes']
 if len(boxes)!=1:raise ValueError('Selected artifact gear support finite scope')
 box=boxes[0]
 item=c.item(BOX)
 if (box['template'],box['name'],box['item_type'],box['metadata'],box['group'],box['max_stack'],box['selection_count'])!=(BOX,item['name'],7,0,4,99,0):raise ValueError('Selected artifact gear support original box')
 if (item['item_type']!=7 or item['metadata']!=0 or hashlib.sha256(item['record']).hexdigest()!=box['record_sha256']):raise ValueError('Selected artifact gear support native box record')
 entries=box['entries']
 if [r['template'] for r in entries]!=list(OUTPUTS) or [r['quantity'] for r in entries]!=list(QUANTITIES):raise ValueError('Selected artifact gear support finite outputs')
 for r,quantity in zip(entries,QUANTITIES):
  piece=c.item(r['template'])
  if (piece['name'],piece['item_type'],piece['metadata'],r['quantity'],r['group'],r['max_stack'])!=(r['name'],2,0,quantity,1,1):raise ValueError('Selected artifact gear support native piece')
  if hashlib.sha256(piece['record']).hexdigest()!=r['record_sha256']:raise ValueError('Selected artifact gear support piece record')
 return MappingProxyType(dict(box=MappingProxyType(box),entries=tuple(MappingProxyType(r) for r in entries)))
def enabled():return True

def entry():
 d=definition()
 return MappingProxyType(dict(template=BOX,name=d['box']['name'],mode='fixed',selection_count=0,
  entries=tuple(dict(template=r['template'],quantity=r['quantity'],name=r['name']) for r in d['entries']),
  artifact_gear_support=True))
