"""Four current job convenience boxes, with explicitly approved local ID mapping."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import client_data,CLIENT_SHA

BOXES=frozenset((300645,300646,300647,300648))
NEW_OUTPUTS=frozenset((300640,300643,300644,190414,190416,183404,183405,183406,183407))
POLICY='human-approved-job-convenience-IDs-20261028-v1'
DATA_SHA='54cc26eea34b26df7435b85cc1ee1d0ef600afbbf514179e05a73abfc85aca60'

@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/job_reward_boxes.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Job convenience mapping identity')
 source=json.loads(raw);client=client_data()
 if (source['policy']!=POLICY or source['client_sha256']!=CLIENT_SHA
     or source['catalog_sha256']!=client.manifest['catalog_sha256']
     or set(map(int,source['boxes']))!=BOXES):raise ValueError('Job convenience original client')
 for row in source['readers']:
  item=client.item(row['template'])
  if (hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']
      or (item['name'],item['metadata'])!=(row['name'],row['metadata'])
      or row['native_reader_ok']!=1 or row['consumed']!=304
      or (row['source_group'],row['group'],row['max_stack'])!=((7,27,1)if row['template']in range(183404,183408)else(4,4,1000)if row['template']==710132 else(4,4,1))):
   raise ValueError('Job convenience exact original output')
 if {r['template']for r in source['readers']}!=NEW_OUTPUTS|{710132}:raise ValueError('Job convenience reader scope')
 for key,row in source['boxes'].items():
  if hashlib.sha256(client.item(int(key))['record']).hexdigest()!=row['record_sha256']:raise ValueError('Job convenience exact box')
 return source

def definitions():return tuple(r for r in catalog()['readers']if r['template']in NEW_OUTPUTS)

def entries():
 return tuple(dict(template=int(key),selection_count=0,job_convenience=True,
     entries=tuple(dict(r)for r in row['outputs']))for key,row in sorted(catalog()['boxes'].items()))

def plan_for(template,epoch):
 from els_server.domain.item_expiration import validate
 if type(template)is not int or template not in BOXES or type(epoch)is not int or epoch<0:raise ValueError('Job convenience opening identity')
 readers={r['template']:r for r in catalog()['readers']};result=[]
 for output in catalog()['boxes'][str(template)]['outputs']:
  r=readers[output['template']];p=dict(template=r['template'],metadata=r['metadata'],group=r['group'],quantity=output['quantity'])
  if output['inventory_days']:p['expires_at']=validate(epoch+output['inventory_days']*86400)
  result.append(p)
 return result

def authorize_output(template,source):
 # Reuse the established transaction-bound owned-box capability. This never
 # opens shop, quest, GM, ordinary loot, or another box as an extra producer.
 if source is None:return False
 from els_server.domain.raid_reward_items import validate_source
 source=validate_source(source);identity=json.loads(source._source)
 if (source.kind!='box' or identity.get('policy')!=POLICY or identity.get('definition_sha256')!=DATA_SHA
     or identity.get('template')not in BOXES or identity.get('owner')!=source.owner
     or type(identity.get('epoch'))is not int or type(identity.get('uid'))is not int):
  raise ValueError('Exact job convenience owned-box source required')
 plan=plan_for(identity['template'],identity['epoch']);source.validate_plan(plan)
 if template not in {r['template']for r in plan}:raise ValueError('Output outside exact job convenience box')
 return True
