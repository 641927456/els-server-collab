"""Existing growth reward710106 only; no new item source or legacy admission."""
import functools,hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data
from els_server.domain.activity_2026_stack_policy import effective_stack
TEMPLATE=710106
DEFINITION_SHA256='95e976536d02ea3150012b878e67a26fd100608dfa0c3be2e6131cf3edea3666'
class RewardCoin:
 def __init__(self,raw):
  if type(raw)is not bytes or hashlib.sha256(raw).hexdigest()!=DEFINITION_SHA256:raise ValueError('Pinned native reset-item definitions required')
  data=json.loads(raw);c=client_data();row=next(r for r in data['templates']if r['template']==TEMPLATE);item=c.item(TEMPLATE)
  if(data['catalog_sha256']!=c.manifest['catalog_sha256']or TEMPLATE not in data['original_groups']['coin']or row['kind']!='coin' or(row['metadata'],row['group'])!=(2,4)or item['metadata']!=2 or item['name']!=row['name']or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']):raise ValueError('Selected reward coin identity')
  from els_server.domain.inventory_items import VERIFIED_TEMPLATES as meta,TEMPLATE_BAG_GROUPS as groups,TEMPLATE_MAX_STACKS as stacks
  if(meta.get(TEMPLATE),groups.get(TEMPLATE),stacks.get(TEMPLATE))!=(2,4,effective_stack(row['max_stack_local'])):raise ValueError('Existing published reward coin registration required')
  self.digest=hashlib.sha256((DEFINITION_SHA256+':growth-reward710106-only-v1').encode()).hexdigest()
  self.allowed=MappingProxyType({'coin':frozenset((TEMPLATE,))})
  self.groups=MappingProxyType({'coin':(TEMPLATE,)})
@functools.lru_cache(maxsize=1)
def reset_items():return RewardCoin((Path(__file__).resolve().parents[1]/'data/resonance2026-reset-items.json').read_bytes())
