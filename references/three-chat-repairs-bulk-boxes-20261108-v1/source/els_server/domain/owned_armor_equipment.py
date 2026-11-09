"""Four armor and ten weapon outputs witnessed in original offline consumers."""
import functools,hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data,CLIENT_SHA
TEMPLATES=frozenset(range(100004679,100004693))
PROOF_SHA='a14aa5c06262467ab2a5e6b88f7abc257bac01506657fc25b43e1a7a4ba6963b'
CATALOG_SHA='a633289850ef5b814aa338542e5f80e641153e99734c4f5c8c82f62bde49c3ba'

@functools.lru_cache(maxsize=1)
def evidence():
 raw=(Path(__file__).resolve().parents[1]/'data/owned_armor_equipment.json').read_bytes();p=json.loads(raw)
 if (hashlib.sha256(raw).hexdigest()!=PROOF_SHA or client_data().manifest['catalog_sha256']!=CATALOG_SHA
     or not p['ok'] or p['live_process_access'] or not p['native_code_executed']
     or len(p['rows'])!=14 or {r['template']for r in p['rows']}!=TEMPLATES):raise ValueError('Owned equipment proof identity')
 for r in p['rows']:
  item=client_data().item(r['template']);record=item['record']
  if (hashlib.sha256(record).hexdigest()!=r['record_sha256'] or (item['item_type'],item['metadata'],record[0xd8])not in((2,0,3),(1,0,4))
      or (r['group'],r['maximum'],r['category77'])!=(1,10000,0)
      or r['instance']!=[[o,d,1]for o in(-1,0,1)for d in(0,10000)]
      or r['defaults']!=dict(enhancement=0,extraStage=0,bonusFlag=1)
      or int.from_bytes(record[0xb0:0xb4],'little') or len(r['attributes'])!=36):raise ValueError('Owned armor native instance evidence')
  capacity=record[0xd8]
  expected=[dict(size=s,consumed=s,metadata=0,slots=slots,restriction=0,level_value=0)for s,slots in((304,[0]*4),(320,[1]*capacity+[0]*(4-capacity)))]
  if r['cases']!=expected:raise ValueError('Owned armor native DTO evidence')
 return p

def definitions():
 evidence();return {t:MappingProxyType(dict(template=t,metadata=0,group=1,max_stack=1))for t in TEMPLATES}

def stat_templates():
 evidence();return TEMPLATES

def wear_proof():
 p=evidence();fields=('template','record_sha256','flags4','flags8','mode','level','unit_type','unit_class','generic_model','models')
 rows=[]
 for r in p['rows']:
  cases=r['wear']if r['mode']==1 else[c for c in r['wear']if c[0]in(r['unit_class'],2 if r['unit_type']==1 else 1)]
  rows.append(dict(**{k:r[k]for k in fields},cases=cases))
 count=sum(len(r['cases'])for r in rows)
 manifest=dict(schema_version=1,client_sha256=CLIENT_SHA,source_catalog_sha256=CATALOG_SHA,predicate_rva='0x868240',rightclick_rva='0x220ebd0',ordinary_town_only=True,authorizes_equipment_move=False,count=14,case_count=count)
 proof=dict(schema_version=1,client_sha256=CLIENT_SHA,probe_version=2,applied_to_game=False,count=14,case_count=count,rows=rows)
 return manifest,proof
