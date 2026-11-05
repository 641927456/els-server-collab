"""127273 purchase-immediate page effect on the existing local ED storefront.

Native KIM says purchase adds1page immediately to the current character.
SKU/ED pricing and cap reuse the explicit local ordinary-page policy; these
are not retail cash entitlements or an invented manual219 coupon use.
"""
import hashlib
from els_server.domain.ordinary_skill_pages import POLICY,EXPAND_ED,MAX_PAGES

TEMPLATE=127273
SKU=1200127273
SOURCE_SHA='e7a21ea7b642edbd8cf25c8c1a74de7010c7b2066cd3094dba9c9e813903664c'

def offer():
    from els_server.game_data import client_data
    item=client_data().item(TEMPLATE)
    if (POLICY!='ordinary-skill-pages-local-20261024-v1' or EXPAND_ED!=10000000 or MAX_PAGES!=3
        or (item['name'],item['metadata'],item['item_type'])!=('技能页扩张券',2,7)
        or hashlib.sha256(item['record']).hexdigest()!=SOURCE_SHA):
        raise ValueError('Skill page instant service source/policy')
    return dict(sku=SKU,template=TEMPLATE,name=item['name'],category=41,price=EXPAND_ED,quantity=1)
