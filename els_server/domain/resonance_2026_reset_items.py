"""Owned published ERP reset coins; no new item source or inventory admission."""
import functools,hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data
from els_server.domain.activity_2026_stack_policy import effective_stack
TEMPLATE=710106
TEMPLATES=(710106,163563)
DEFINITION_SHA256='95e976536d02ea3150012b878e67a26fd100608dfa0c3be2e6131cf3edea3666'
class RewardCoin:
 def __init__(self,raw):
  if type(raw)is not bytes or hashlib.sha256(raw).hexdigest()!=DEFINITION_SHA256:raise ValueError('Pinned native reset-item definitions required')
  data=json.loads(raw);c=client_data()
  from els_server.domain.inventory_items import VERIFIED_TEMPLATES as meta,TEMPLATE_BAG_GROUPS as groups,TEMPLATE_MAX_STACKS as stacks
  for template in TEMPLATES:
   row=next(r for r in data['templates']if r['template']==template);item=c.item(template)
   if(data['catalog_sha256']!=c.manifest['catalog_sha256']or template not in data['original_groups']['coin']or row['kind']!='coin' or(row['metadata'],row['group'])!=(2,4)or item['metadata']!=2 or item['name']!=row['name']or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']):raise ValueError('Selected published coin identity')
   if(meta.get(template),groups.get(template),stacks.get(template))!=(2,4,effective_stack(row['max_stack_local'])):raise ValueError('Existing published coin registration required')
  self.digest=hashlib.sha256((DEFINITION_SHA256+':published-coins710106-163563-v2').encode()).hexdigest()
  # Old committed reward-coin receipts are immutable and remain replayable.
  self.legacy_digests=(hashlib.sha256((DEFINITION_SHA256+':growth-reward710106-only-v1').encode()).hexdigest(),)
  self.allowed=MappingProxyType({'coin':frozenset(TEMPLATES)})
  self.groups=MappingProxyType({'coin':TEMPLATES})
@functools.lru_cache(maxsize=1)
def reset_items():return RewardCoin((Path(__file__).resolve().parents[1]/'data/resonance2026-reset-items.json').read_bytes())
