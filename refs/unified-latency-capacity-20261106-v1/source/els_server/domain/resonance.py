"""Current-client ERP curve; no replicated skill/effect calculations."""
import bisect,functools,struct,hashlib,json
from pathlib import Path

@functools.lru_cache(maxsize=1)
def experience_multiplier():
 # User local economy policy, independent of ordinary EXP and GM settings.
 p=Path(__file__).resolve().parents[1]/'data/resonance_experience.json'
 v=json.loads(p.read_bytes())
 if v!={'schema_version':1,'policy':'user-local-resonance-only-10x-v1','provenance':'explicit_user_local_rule','resonance_multiplier':10,'ordinary_multiplier':1,'sources':['kill','clear'],'retroactive_top_up':False}:raise ValueError('Unreviewed local ERP multiplier policy')
 return v['resonance_multiplier']

@functools.lru_cache(maxsize=1)
def book_definitions():
 from els_server.game_data import client_data,CLIENT_SHA
 data=client_data();p=Path(__file__).resolve().parents[1]/'data/resonance_books.json';proof=json.loads(p.read_bytes())
 if proof['client_sha256']!=CLIENT_SHA or proof['catalog_sha256']!=data.manifest['catalog_sha256'] or proof['new_acquisition_providers'] or not proof['existing_owned_items_only']:raise ValueError('ERP book evidence scope')
 if {x['template'] for x in proof['rows']}!={163561,163562,300891}:raise ValueError('ERP book scope')
 for row in proof['rows']:
  item=data.item(row['template'])
  if hashlib.sha256(item['record']).hexdigest()!=row['record_sha256'] or (item['metadata'],item['item_type'],row['group'],row['max_stack'])!=(0,7,4,1) or row['consumed']!=304 or not row['fields_match']:raise ValueError('ERP book native evidence')
 return tuple(proof['rows'])

@functools.lru_cache(maxsize=1)
def curve():
 from els_server.game_data import client_data
 data=client_data();source=next(x for x in data.manifest['sources'] if x['name']=='ElResonanceEXPTable.lua')
 if source['sha256']!='04b870a55ea9c2335b72eb60e95dd465ec6abd44419fa6759062ee983bf8da99':raise ValueError('Unreviewed ERP curve source')
 rows=[]
 for row in data.resonance_curve():
  if any(type(row[k]) not in (int,float) or int(row[k])!=row[k] for k in ('ER_LEVEL','NEED_ER_EXP','TOTAL_ER_EXP')):raise ValueError('Nonintegral ERP source')
  rows.append({k:int(v) for k,v in row.items()})
 if len(rows)!=1000 or [x['ER_LEVEL'] for x in rows]!=list(range(1,1001)):raise ValueError('ERP curve coverage')
 if any(rows[i]['TOTAL_ER_EXP']-rows[i-1]['TOTAL_ER_EXP']!=rows[i]['NEED_ER_EXP'] for i in range(1,len(rows))):raise ValueError('ERP curve cumulative identity')
 return tuple(rows[:999])

def limit():return curve()[-1]['TOTAL_ER_EXP']
def level(experience):
 if type(experience) is not int or not 0<=experience<=limit():raise ValueError('ERP signed64 cumulative bound')
 return min(999,bisect.bisect_right([r['TOTAL_ER_EXP'] for r in curve()],experience))

def wire(state):
 if not isinstance(state,dict):raise ValueError('ERP state')
 enabled=state['enabled'];xp=state['experience'];lv=state['level'];aux=state['auxiliary']
 if type(enabled) is not bool or type(aux) is not int or aux!=0:raise ValueError('ERP enable/default auxiliary state')
 if type(xp) is not int or type(lv) is not int or (enabled and lv!=level(xp)) or (not enabled and (lv or xp)):raise ValueError('ERP curve/state disagreement')
 # Current D9B170 DTO471 -> original87C8EE -> player2861/2865/2871.
 # The trailing i32 remains the existing zero default; it is not ERP points.
 return struct.pack('>iQiB',lv,xp,aux,enabled)

