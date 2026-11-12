"""Current-client ERP reset coin definitions used by the native 611 transaction."""
import functools,hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data
from els_server.domain.activity_2026_stack_policy import effective_stack
TEMPLATE=710106
PUBLISHED_TEMPLATES=(710106,163563,710105)
# Remaining native section-reset records with a current item body.
RETAINED_TEMPLATES=(712422,190046,297077,165816,165728,163565,300892,710107,710104)
TEMPLATES=PUBLISHED_TEMPLATES+RETAINED_TEMPLATES
DEFINITION_SHA256='95e976536d02ea3150012b878e67a26fd100608dfa0c3be2e6131cf3edea3666'

def coin_definitions(raw):
 if type(raw)is not bytes or hashlib.sha256(raw).hexdigest()!=DEFINITION_SHA256:raise ValueError('Pinned native reset-item definitions required')
 data=json.loads(raw);c=client_data()
 result={}
 for template in TEMPLATES:
  row=next(r for r in data['templates']if r['template']==template);item=c.item(template)
  if(data['catalog_sha256']!=c.manifest['catalog_sha256']or template not in data['original_groups']['coin']or row['kind']!='coin' or(row['metadata'],row['group'])!=(2,4)or item['metadata']!=2 or item['name']!=row['name']or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']):raise ValueError('Selected published coin identity')
  # Keep the original account-quest coin's native cap and the formal cap for
  # the other two existing reset variants.
  cap=300 if template==710105 else effective_stack(row['max_stack_local'])
  result[template]=(row['metadata'],row['group'],cap)
 return result

def source_bytes():return (Path(__file__).resolve().parents[1]/'data/resonance2026-reset-items.json').read_bytes()

class RewardCoin:
 def __init__(self,raw):
  from els_server.domain.inventory_items import VERIFIED_TEMPLATES as meta,TEMPLATE_BAG_GROUPS as groups,TEMPLATE_MAX_STACKS as stacks
  for template,definition in coin_definitions(raw).items():
   if(meta.get(template),groups.get(template),stacks.get(template))!=definition:raise ValueError('Existing published coin registration required')
  self.digest=hashlib.sha256((DEFINITION_SHA256+':current-owned-reset-coins-v4').encode()).hexdigest()
  # Old committed reward-coin receipts are immutable and remain replayable.
  self.legacy_digests=tuple(hashlib.sha256((DEFINITION_SHA256+suffix).encode()).hexdigest()for suffix in(':published-coins710106-163563-710105-v3',':published-coins710106-163563-v2',':growth-reward710106-only-v1'))
  self.allowed=MappingProxyType({'coin':frozenset(TEMPLATES)})
  self.groups=MappingProxyType({'coin':TEMPLATES})
@functools.lru_cache(maxsize=1)
def reset_items():return RewardCoin(source_bytes())
