"""Current400152 native donation and its one-for-one400154 output only."""
import hashlib,json
from functools import lru_cache
COIN=400152
SEED=400154
POLICY='native-current-guild-coin-donation-20261028-v1'
@lru_cache(maxsize=1)
def definitions():
 from els_server.game_data import client_data,CLIENT_SHA
 if CLIENT_SHA!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709':raise ValueError('Guild coin client build')
 c=client_data()
 for template,digest in ((COIN,'d19bb054b095cea9e29a8c8e4bc0c441dbfdc18938d2247e27bbafe84e52d07b'),(SEED,'8e17e3a8445986d4753c42c0e4d27e1ddd904d6be42bc02e098840a069cde1ae')):
  row=c.item(template)
  if (row['metadata'],row['item_type'])!=(2,7)or hashlib.sha256(row['record']).hexdigest()!=digest:raise ValueError('Guild coin exact native definition')
 return True
def plan(quantity):
 if type(quantity)is not int or not 1<=quantity<=500:raise ValueError('Guild coin original stack bound')
 definitions();return[dict(template=SEED,quantity=quantity,metadata=2,group=4)]
def authorize_output(template,source):
 if template!=SEED or source is None:return False
 from els_server.domain.raid_reward_items import validate_source
 source=validate_source(source);r=json.loads(source._source)
 if(source.kind!='guild_donation'or r.get('policy')!=POLICY or r.get('template')!=COIN or r.get('owner')!=source.owner or type(r.get('guild_id'))is not int or r['guild_id']<=0 or type(r.get('uid'))is not int or r['uid']<=0):raise ValueError('Guild seed exact donation source')
 source.validate_plan(plan(r.get('quantity')));return True
