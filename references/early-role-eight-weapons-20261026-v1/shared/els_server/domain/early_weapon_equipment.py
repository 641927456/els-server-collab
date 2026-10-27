"""Eight current zero-element-capacity weapons, independently witnessed.

The historical normal-enchant catalog remains pinned to capacities1..4.
This appendix changes neither element capacity nor normal magic-stone sockets.
"""
import functools,hashlib,json
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA
TEMPLATES=frozenset((11022316,11022323,11022324,11022331,11022412,11022419,11022420,11022427))

@functools.lru_cache(maxsize=1)
def evidence():
 m=json.loads((PROJECT_ROOT/'els_server/data/early_weapon_equipment.json').read_bytes());raw=(PROJECT_ROOT/m['proof']).read_bytes();p=json.loads(raw)
 if (m['schema_version']!=1 or m['client_sha256']!=CLIENT_SHA or p['client_sha256']!=CLIENT_SHA or m['source_catalog_sha256']!=client_data().manifest['catalog_sha256'] or hashlib.sha256(raw).hexdigest()!=m['proof_sha256'] or m['count']!=8 or set(m['templates'])!=TEMPLATES or not p['ok'] or p['live_process_access'] or p['player_save_access'] or p['formal_mutations'] or not p['native_code_executed']):raise ValueError('Early weapon appendix identity')
 for name in ('normal_rows','eligibility_rows','instance_rows','details'):
  if len(p[name])!=8 or {r['template']for r in p[name]}!=TEMPLATES:raise ValueError('Early weapon appendix finite coverage')
 rows={r['template']:r for r in p['normal_rows']};instances={r['template']:r for r in p['instance_rows']}
 category=p['classification_source77']
 if (category['m_eType'],category['m_eReadType'])!=(77,1) or TEMPLATES&set(category['m_eItemID'].values()):raise ValueError('Early weapon PC-room restriction')
 for d in p['details']:
  t=d['template'];item=client_data().item(t);rec=item['record'];r=rows[t];i=instances[t]
  if (d['record_sha256']!=hashlib.sha256(rec).hexdigest() or d['record_hex']!=rec.hex() or (item['item_type'],item['metadata'],item['equip_position'],rec[0xd8])!=(1,1,2,0) or int.from_bytes(rec[4:8],'little')&161 or rec[0xd3]not in(203,204) or r['source']!=dict(template=t,flags4=item['flags4'],flags8=item['flags8'],metadata=1,capacity=0,level=rec[0xd1],level_override=rec[0xd9],record_sha256=d['record_sha256']) or (r['accepted'],r['group'],r['metadata'],r['capacity'])!=(True,1,1,0)):raise ValueError('Early weapon original record')
  if r['cases']!=[dict(size=s,consumed=s,slots=[0]*4,restriction=0,level_value=0)for s in(304,320)]:raise ValueError('Early weapon native inventory cases')
  if (i['category77'],i['accountState'],i['special'])!=(0,0,False) or i['cases']!=[[o,dur,int(dur>0)]for o in(-1,0,1)for dur in(0,10000)]:raise ValueError('Early weapon native instance cases')
 return p,m

def definitions():
 evidence();return {t:MappingProxyType(dict(template=t,metadata=1,group=1,max_stack=1))for t in TEMPLATES}

def stat_templates():
 p,_=evidence()
 # These exact templates carry no template-effect list. Default new instances
 # have enhancement0, extraStage0 and no saved additional option vectors.
 # Reuse the existing generic native-relative calculation and coefficients.
 if any(int.from_bytes(client_data().item(t)['record'][0xb0:0xb4],'little') for t in TEMPLATES):raise ValueError('Early weapon template effects changed')
 if any(d['defaults']!=dict(enhancement=0,extraStage=0,bonusFlag=1)for d in p['details']):raise ValueError('Early weapon native default instance changed')
 if len(p['stat_suffix_rows'])!=8 or {r['template']for r in p['stat_suffix_rows']}!=TEMPLATES or p['stat_suffix_range']!=['0x198c3bd','0x198c521']:raise ValueError('Early weapon native stat suffix evidence')
 return TEMPLATES

def wear_proof():
 p,m=evidence();rows=p['eligibility_rows'];count=sum(len(r['cases'])for r in rows)
 manifest=dict(schema_version=1,client_sha256=CLIENT_SHA,source_catalog_sha256=m['source_catalog_sha256'],predicate_rva='0x868240',rightclick_rva='0x220ebd0',ordinary_town_only=True,authorizes_equipment_move=False,count=8,case_count=count)
 proof=dict(schema_version=1,client_sha256=CLIENT_SHA,probe_version=2,applied_to_game=False,count=8,case_count=count,rows=rows)
 return manifest,proof
