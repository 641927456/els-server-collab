"""Four source-qualified regular palettes, existing ordinary local50ED policy.

No retail88-cash conversion, event variants, seasonal color revival or UI change.
"""
import hashlib,functools
from types import MappingProxyType

TEMPLATES=(481213,481214,482109,482110)
PRICE=50
CATEGORY=37 # Same-build105 CSSC_CONSUME_DYEING -> real37.
POLICY='existing-ordinary-permanent-shop50ED-four-regular-palettes-v1'
EXPECTED={
 481213:('染发调色板（日常）',True,1,'11059af5a8cad6277d443eba7a2a18340522ee40df044dc1c7bcf082f708a65a'),
 481214:('染发调色板（自然）',True,2,'f0249463bdd3ab2acfdf3539640b1184284fd6762cdf0e2cf1af6c3eacfc8a1d'),
 482109:('时装调色板（日常）',False,1,'f3e52c140bace077d100512088538791e3a9ecdd35a817e9377c4cbbe1189693'),
 482110:('时装调色板（自然）',False,2,'fe55644556c984e76ad0e1af5eb523698c9ae3a4ea3c6813428978bfa8b8a0f5'),
}

@functools.lru_cache(maxsize=1)
def offers():
    from els_server.game_data import client_data
    from els_server.domain.wardrobe_extensions import catalog
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
    data=catalog();client=client_data();result=[]
    for template in TEMPLATES:
        name,hair,group,digest=EXPECTED[template];item=client.item(template)
        if (item['name']!=name or hashlib.sha256(item['record']).hexdigest()!=digest
            or data['palettes'][str(template)]!={'hair':hair,'group':group}
            or data['consumables'][str(template)]['record_sha256']!=digest
            or (VERIFIED_TEMPLATES[template],TEMPLATE_BAG_GROUPS[template],TEMPLATE_MAX_STACKS[template])!=(2,4,999)):
            raise ValueError('Regular palette current native source mismatch')
        result.append(MappingProxyType(dict(sku=1200000000+template,template=template,name=name,category=CATEGORY,price=PRICE,quantity=1)))
    return tuple(result)

def guarded_request(payload):
    from els_server.protocol.shop_messages import ed_purchase_request
    skus={1200000000+t for t in TEMPLATES}
    skus.update(1500000000+4*t+index for t in TEMPLATES for index in(1,2,3))
    return any(sku in skus for sku,n in ed_purchase_request(payload))

def purchase_context(session,event,sequence):
    if (type(sequence)is not int or not 1<=sequence<2**32 or event.performers not in((),(0,))
        or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0):
        raise ValueError('Palette purchase envelope')
    from els_server.domain.tenebros_capacity_flow import selected
    path,owner,account_id,current=selected(session)
    def prepare(db):
        current(db)
        from els_server.storage.item_actor import require_active_character
        from els_server.storage.profession_state import require_owner
        require_active_character(db,owner);require_owner(db,owner,account_id)
    return prepare
