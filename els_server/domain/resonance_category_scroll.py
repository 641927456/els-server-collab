"""Existing ordinary163564 only; no new source or reward-item admission."""
from functools import lru_cache
import hashlib,json
from pathlib import Path
from types import MappingProxyType
from els_server.game_data import client_data
from els_server.domain.activity_2026_stack_policy import effective_stack
DEFINITION_SHA256='95e976536d02ea3150012b878e67a26fd100608dfa0c3be2e6131cf3edea3666'
ORIGINAL_ORDER=(712423,163566,163542,710112,710111,710110,163564,710109)
TEMPLATE=163564

class OrdinaryScroll:
    def __init__(self,raw):
        if type(raw)is not bytes or hashlib.sha256(raw).hexdigest()!=DEFINITION_SHA256:
            raise ValueError('Pinned original category scroll table required')
        data=json.loads(raw);row=next(r for r in data['templates']if r['template']==TEMPLATE)
        c=client_data();item=c.item(TEMPLATE)
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES as meta,TEMPLATE_BAG_GROUPS as bags,TEMPLATE_MAX_STACKS as stacks
        if (tuple(data['original_groups']['scroll'])!=ORIGINAL_ORDER
            or data['catalog_sha256']!=c.manifest['catalog_sha256']
            or (row['kind'],row['metadata'],row['group'])!=('scroll',2,4)
            or item['metadata']!=2 or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']
            or (meta.get(TEMPLATE),bags.get(TEMPLATE),stacks.get(TEMPLATE))!=(2,4,effective_stack(row['max_stack_local']))):
            raise ValueError('Existing ordinary category scroll identity or registration changed')
        self.digest=hashlib.sha256((DEFINITION_SHA256+':ordinary163564-positive-category-only-v1').encode()).hexdigest()
        self.allowed=MappingProxyType({'scroll':frozenset((TEMPLATE,))})
        self.groups=MappingProxyType({'scroll':ORIGINAL_ORDER})

@lru_cache(maxsize=1)
def scroll_items():
    return OrdinaryScroll((Path(__file__).resolve().parents[1]/'data/resonance2026-reset-items.json').read_bytes())
