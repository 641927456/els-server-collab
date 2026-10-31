"""Finite current ordinary economy; missing exact probabilities are local rules."""
import functools,hashlib,json,struct,uuid
from pathlib import Path
@functools.lru_cache(maxsize=1)
def policy():
 p=Path(__file__).resolve().parents[1]/'data/formal_pve_economy.json';raw=p.read_bytes();d=json.loads(raw);m=json.loads(p.with_suffix('.manifest.json').read_bytes())
 from els_server.game_data import client_data,CLIENT_SHA
 if(d['schema_version']!=1 or d['policy']!='formal-ordinary-economy-20261025-v1'or d['client_sha256']!=CLIENT_SHA or m['client_sha256']!=CLIENT_SHA or hashlib.sha256(raw).hexdigest()!=m['payload_sha256']or d['catalog_sha256']!=client_data().manifest['catalog_sha256']or len(d['maps'])!=159):raise ValueError('Ordinary economy exact policy identity')
 for key,row in d['items'].items():
  item=client_data().item(int(key))
  if hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']or item['name']!=row['name']or item['metadata']!=row['metadata']:raise ValueError('Ordinary economy current item identity')
 from els_server.domain.native_ticket_rules import definitions as _ticket_definitions
 if (118341 not in _ticket_definitions()[35100] or
     '118341' in d['held_display_items'] or
     d['items']['118341']['wear_family']!=0):raise ValueError('Native Torta ticket source/reader changed')
 for _map in (35080,35090):
  _row=d['maps'][str(_map)];_source=client_data().dungeon(_map)
  if (not _row['additional_clear_drop'] or not _row['additional_group_clear_drop'] or
      118341 not in _row['current_display_pool']['COMMON'] or
      118341 not in _source['BOSS_DROP_ITEM']['COMMON'].values() or
      _row['current_definition_sha256']!=hashlib.sha256(client_data()._definition('dungeons','id',_map).encode()).hexdigest() or
      '118341' in _row['held_display_items']):raise ValueError('Original Torta ticket clear source changed')
 for _map in (35340,35350):
  _row=d['maps'][str(_map)];_source=client_data().dungeon(_map)
  if (_row['additional_clear_drop'] or not _row['additional_group_clear_drop'] or
      118651 not in _row['current_display_pool']['COMMON'] or
      118651 not in _source['BOSS_DROP_ITEM']['COMMON'].values() or
      _row['current_definition_sha256']!=hashlib.sha256(client_data()._definition('dungeons','id',_map).encode()).hexdigest() or
      '118651' in _row['held_display_items'] or
      118651 not in _ticket_definitions()[35360] or d['items']['118651']['wear_family']!=0):raise ValueError('Original Garden group-only ticket clear source changed')
 d['_sha256']=m['payload_sha256'];return d
def definition(identity):
 d=policy()['maps'].get(str(identity))
 return None if d is not None and d.get('special_authority_preserved')=='silver_mirror'else d
def check_run(run):
 d=definition(run.identity)
 if d is None:return None
 if run.graph['source_sha256']!=d['graph_sha256']or run.legacy_experience is None:raise ValueError('Ordinary economy original graph/EXP binding')
 return d
def coin(identity,boss,fallback):
 d=policy()['maps'].get(str(identity))
 if d is None:return fallback
 p=policy()['local'];return min(2**31-1,d['coin_base_level']**2*p['ordinary_coin_level_squared_multiplier']*(p['boss_coin_multiplier']if boss else 1))
def clear_bonus(total):
 if type(total)is not int or total<0:raise ValueError('Ordinary committed kill EXP bound')
 f32=lambda v:struct.unpack('<f',struct.pack('<f',v))[0]
 return min(2**31-1,int(f32(f32(total)*f32(0.3))))
def clear_items(identity,run_id,owner,character,group=False,*,drop_bp=0):
 from els_server.domain.reward_rules import item_plan
 from els_server.game_data import client_data
 d=definition(identity)
 if d is None or not d['additional_group_clear_drop'if group else'additional_clear_drop']:return []
 p=policy();family=client_data().unit(character['unit_class'])['unitType']
 pool=sorted({t for values in d['current_display_pool'].values()for t in values if p['items'][str(t)]['wear_family']in(0,family)})
 seed=uuid.UUID(run_id).bytes+f':{identity}:{owner}:ordinary-clear-v1'.encode();digest=hashlib.sha256(seed).digest()
 if type(drop_bp)is not int or not 0<=drop_bp<=10000:raise ValueError('Ordinary clear drop bonus')
 scale=100000000 if drop_bp else 10000;threshold=min(scale,p['local']['current_boss_display_completion_bp']*(10000+drop_bp))if drop_bp else p['local']['current_boss_display_completion_bp']
 if not pool or int.from_bytes(digest[:16],'big')%scale>=threshold:return []
 return [item_plan(pool[int.from_bytes(digest[16:],'big')%len(pool)],p['local']['quantity'])]
