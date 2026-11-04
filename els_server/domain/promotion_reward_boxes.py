"""Human-approved server mappings for four current career reward boxes."""
import functools,hashlib,json
from pathlib import Path
BOXES=frozenset((109999,110850,135867,135869))
POLICY='human-approved-four-job-box-mapping-20261028-v1'
DATA_SHA='dc80c4007fa65d4be6686c177c5bd75418d53bd4e7c61236501d038eff27130d'
@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/promotion_reward_boxes.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Career box mapping checksum')
 data=json.loads(raw)
 from els_server.game_data import client_data,CLIENT_SHA
 c=client_data()
 if data['policy']!=POLICY or data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=c.manifest['catalog_sha256']or set(map(int,data['boxes']))!=BOXES:raise ValueError('Career box current client identity')
 for row in data['readers']:
  if hashlib.sha256(c.item(row['template'])['record']).hexdigest()!=row['record_sha256']or row['native_reader_ok']!=1 or row['consumed']!=304:raise ValueError('Career box native item identity')
 return data
@functools.lru_cache(maxsize=1)
def definitions():return tuple(r for r in catalog()['readers']if not r['previously_registered'])
@functools.lru_cache(maxsize=1)
def new_templates():return frozenset(r['template']for r in definitions())
def reader_map():return{r['template']:r for r in catalog()['readers']}
def outputs_for(template,unit_class):
 rows=[r for r in catalog()['groups']if r['box']==template and unit_class in r['classes']]
 if len(rows)!=1:raise ValueError('Career box original class group unavailable')
 return rows[0]['outputs']
def plan_for(template,epoch,unit_class):
 from els_server.domain.item_expiration import validate
 if type(epoch)is not int or epoch<0:raise ValueError('Career box clock')
 readers=reader_map();result=[]
 for output in outputs_for(template,unit_class):
  row=readers[output['template']];p=dict(template=row['template'],metadata=row['metadata'],group=row['group'],quantity=output['quantity'])
  if output['inventory_days']:p['expires_at']=validate(epoch+86400*output['inventory_days'])
  result.append(p)
 return result
def authorize_output(template,source):
 if source is None:return False
 from els_server.domain.raid_reward_items import validate_source
 source=validate_source(source);identity=json.loads(source._source)
 if identity.get('policy')!=POLICY:return False
 if source.kind!='box'or identity.get('definition_sha256')!=DATA_SHA or identity.get('template')not in BOXES or identity.get('owner')!=source.owner or type(identity.get('unit_class'))is not int or type(identity.get('uid'))is not int:raise ValueError('Career box source identity')
 plan=plan_for(identity['template'],identity['epoch'],identity['unit_class']);source.validate_plan(plan)
 if template not in {r['template']for r in plan}:raise ValueError('Career box source output')
 return True
def starter_rules():return{int(k):v for k,v in catalog()['starter_force_rules'].items()}
def common_force():return dict(catalog()['common_force'],starter_common=True,active=True)
