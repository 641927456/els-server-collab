"""Original Henir 4th Dimension identification group and ordinary reset scrolls."""
import functools,hashlib,json
from pathlib import Path
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data
@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/identification_ui.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!='c3e9be1f22a012b32826fd6ddeaa05bec8688fc6a7cd5b19a9259d860e9a0629':raise ValueError('Identification source changed')
 c=json.loads(raw)
 if c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=client_data().manifest['catalog_sha256']:raise ValueError('Identification build mismatch')
 for s in c['sources']:
  if hashlib.sha256((PROJECT_ROOT/s['path']).read_bytes()).hexdigest()!=s['sha256']:raise ValueError('Identification evidence changed')
 for row in [*c['templates'].values(),*c['materials'].values()]:
  if hashlib.sha256(client_data().item(row['template'])['record']).hexdigest()!=row['record_sha256']:raise ValueError('Identification original item mismatch')
 for pool in c.get('pools',{}).values():
  bound=pool['source'];raw_source=bound['raw_json'].encode('utf8')
  if hashlib.sha256(raw_source).hexdigest()!=bound['sha256']:raise ValueError('Identification pool source changed')
  source=json.loads(raw_source)
  if source['code']!=0 or pool['native_group']!=1010 or pool['official_group']!=4 or len(source['data'])!=45 or len(pool['outcomes'])!=45 or len(pool['options'])!=48:raise ValueError('Identification pool identity')
  from decimal import Decimal
  for original,outcome in zip(source['data'],pool['outcomes']):
   if original['webitemid']!=6321 or original['groupno']!=4 or original['option_str']!=outcome['official_label'] or Decimal(original['probability'])*100!=outcome['weight'] or str(outcome['option']) not in pool['options']:raise ValueError('Identification pool outcome mismatch')
  if sum(r['weight'] for r in pool['outcomes'])!=10000:raise ValueError('Identification pool weight total')
 historical=c.get('historical_1020_option_ids')
 if not isinstance(historical,list) or any(type(v) is not int for v in historical) or len(historical)!=45 or set(historical)!={40324, 40836, 40328, 40712, 40714, 40842, 40332, 40716, 40848, 40212, 46612, 40214, 46614, 40216, 46616, 40612, 61220, 40614, 61222, 40616, 61224, 40112, 40114, 40116, 41018, 41021, 40512, 41024, 40514, 40516, 40012, 61260, 40014, 61262, 40016, 61264, 40412, 40414, 40416, 5608, 5609, 5610, 40936, 40942, 40948}:raise ValueError('Identification historical option identity')
 for label,pool in [('1020',c),('1010',c['pools']['1010'])]:
  legacy=pool.get('legacy_outcome_ids');expected={'1020':{41018,41021,41024},'1010':{41009,41012,41015}}[label]
  selected={r['option'] for r in pool['outcomes']}
  if not isinstance(legacy,list) or any(type(v) is not int for v in legacy) or len(legacy)!=3 or set(legacy)!=expected or len(selected)!=45 or selected&expected or set(pool['options'])!={str(v) for v in selected|expected}:raise ValueError('Identification selected and historical options')
 cslots=c['compatibility_slots']
 if cslots['version']!='native-shaped-compatibility-v1' or cslots['pool_reference']!='top-level1020':raise ValueError('Identification compatibility slot identity')
 for key,row in cslots['rows'].items():
  record=client_data().item(int(key))
  if(record['item_type']not in(1,2) or hashlib.sha256(record['record']).hexdigest()!=row['record_sha256']
     or not isinstance(row['native_groups'],list) or not 1<=len(row['native_groups'])<=3
     or any(type(g)is not int or g<=0 for g in row['native_groups'])
     or type(row['pending_projection'])is not bool or type(row['initial_only'])is not bool):raise ValueError('Identification compatibility native slot record')
  if 'pool'in row:
   pool=c['pools'].get(row['pool'])
   if pool is None or row['native_groups']!=[pool['native_group']]*len(row['native_groups']):raise ValueError('Identification compatibility pool mismatch')
 definitions={}
 for source in c['sources'][1:3]:
  definitions.update({str(v['arguments'][1]['ID']):v['arguments'][1] for v in json.loads((PROJECT_ROOT/source['path']).read_bytes())['__symbolic_calls__']})
 def effect(v):return {k:x for k,x in v.items() if k not in('ID','TYPE','m_eDescStringID') and x not in('Group 0',{},[],0,False,None)}
 effects=[effect(v) for v in c['options'].values()]
 for key,value in cslots['historical_alias_definitions'].items():
  if definitions.get(key)!=value or value.get('TYPE')!=1 or effect(value)not in effects:raise ValueError('Identification historical alias identity')
 return c
def template_pool(template):
 c=catalog();profile=c['compatibility_slots']['rows'].get(str(template))
 if profile is not None and 'pool'in profile:
  pool=c['pools'][profile['pool']]
  if profile['native_groups']!=[pool['native_group']]*len(profile['native_groups']):raise ValueError('Identification compatibility pool mismatch')
  return pool
 row=c['templates'].get(str(template))
 if row is None or 'pool' not in row:return None
 pool=c['pools'][row['pool']]
 if row['groups']!=[pool['native_group']] or row['official_group']!=pool['official_group']:raise ValueError('Identification template pool mismatch')
 return pool
def initial_pending(item):
 from els_server.domain.accessory_identification import initial_pending as accessory_pending
 from els_server.domain.boosting_gear_identification import initial_pending as activity_pending
 row=compatibility_profile(item['template'])
 projected=bool(row and row['pending_projection'] and 'identified'not in item and item['group']==1 and item['count']==1 and not item.get('option_groups',{}).get('1',[]))
 return projected or accessory_pending(item) or activity_pending(item)

def require_template(template,*,reset=False):
 from els_server.domain.boosting_gear_identification import supported as activity_supported,catalog as activity_catalog
 if activity_supported(template):activity_catalog();return
 from els_server.domain.accessory_identification import supported
 if supported(template):return
 from els_server.domain.artifact_identification import supported
 if supported(template):return
 row=compatibility_profile(template)
 if row is not None:
  if reset and row['initial_only']:raise ValueError('Unsupported compatibility identification reset')
  return
 if str(template) not in catalog()['templates']:
  from els_server.domain.manufacture_rules import inventory_definitions
  if template not in inventory_definitions() or client_data().item(template)['item_type'] not in (1,2):raise ValueError('Unsupported compatibility identification item')
def validate(template,values):
 from els_server.domain.boosting_gear_identification import supported as activity_supported,validate as activity_validate
 if activity_supported(template):return activity_validate(template,values)
 from els_server.domain.accessory_identification import supported,validate as accessory_validate
 if supported(template):return accessory_validate(template,values)
 from els_server.domain.artifact_identification import supported,validate as artifact_validate
 if supported(template):return artifact_validate(template,values)
 require_template(template)
 row=compatibility_profile(template)
 if row is not None:
  allowed={**catalog()['options'],**catalog()['compatibility_slots']['historical_alias_definitions']}
  pool=template_pool(template)
  if pool is not None:allowed={**allowed,**pool['options']}
  if not isinstance(values,(list,tuple)) or len(values)not in(0,1,len(row['native_groups'])) or any(type(v)is not int or str(v)not in allowed for v in values):raise ValueError('Invalid compatibility identification history vector')
  return list(values)
 allowed=catalog()['options'];pool=template_pool(template)
 if pool is not None:
  legacy=pool.get('legacy_templates')
  if not isinstance(legacy,list) or any(type(t) is not int for t in legacy) or len(legacy)!=20 or set(legacy)!={61857,61858,61859,61860,61861,61862,61863,61864,61865,61866,61948,61949,61950,61951,61952,61953,61954,61955,61956,61957}:raise ValueError('Identification historical compatibility targets')
  historical=catalog()['historical_1020_option_ids']
  allowed={**{str(v):allowed[str(v)] for v in historical},**pool['options']} if template in legacy else pool['options']
 if not isinstance(values,(list,tuple)) or len(values) not in (0,1) or any(type(v) is not int or str(v) not in allowed for v in values):raise ValueError('Invalid original identification vector')
 return list(values)
def select_weighted(rows,roll,denominator,*,range_error,incomplete_error=None):
 # Defer a catalog provider until after entropy validation, as existing callers do.
 if type(roll) is not int or not 0<=roll<denominator:raise ValueError(range_error)
 for row in rows() if callable(rows) else rows:
  if roll<row['weight']:return row['option']
  roll-=row['weight']
 if incomplete_error is not None:raise ValueError(incomplete_error)
 # Artifact's existing draw omits a result if a caller mutates its checked pool.
 return None

def draw_slots(rows,count,randbelow,denominator,*,range_error,incomplete_error=None):
 values=[]
 for unused in range(count):
  value=select_weighted(rows,randbelow(denominator),denominator,
                        range_error=range_error,incomplete_error=incomplete_error)
  if value is not None:values.append(value)
 return values

def draw(roll):
 return select_weighted(lambda:catalog()['outcomes'],roll,10000,
                        range_error='Identification random range',
                        incomplete_error='Identification probabilities incomplete')

def draw_for_template(template,roll):
 pool=template_pool(template)
 if pool is None:return draw(roll)
 return select_weighted(pool['outcomes'],roll,10000,
                        range_error='Identification random range',
                        incomplete_error='Identification probabilities incomplete')

def compatibility_profile(template):
 return catalog()['compatibility_slots']['rows'].get(str(template))

def draw_initial(template,randbelow):
 row=compatibility_profile(template)
 if row is None:return [draw_for_template(template,randbelow(10000))]
 pool=template_pool(template) if 'pool'in row else None
 outcomes=lambda:(pool if pool is not None else catalog())['outcomes']
 values=draw_slots(outcomes,len(row['native_groups']),randbelow,10000,
                   range_error='Identification random range',
                   incomplete_error='Identification probabilities incomplete')
 # New production is exact native shape and selected compatibility IDs only.
 if len(values)!=len(row['native_groups']) or any(v not in {x['option'] for x in outcomes()} for v in values):raise ValueError('Identification generated slot vector')
 return values

def require_initial_complete(item):
 row=compatibility_profile(item['template'])
 if row is None or item.get('identified')is True:return
 if item.get('identified')is False or initial_pending(item):raise ValueError('Equipment requires ordinary initial identification')
 # Preserve legacy read state; never turn a nonempty partial vector into a reroll.
 if row['pending_projection'] and len(item.get('option_groups',{}).get('1',[]))!=len(row['native_groups']):raise ValueError('Incomplete historical identification vector')
