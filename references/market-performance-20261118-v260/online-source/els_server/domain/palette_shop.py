"""Twenty native ordinary palettes, owner-approved permanent shop at 50 ED each.

Seasonal ordinary colors are included; event gift variants are not sold.
"""
import hashlib,functools
from types import MappingProxyType

TEMPLATES=(481213, 481214, 481239, 481283, 481341, 481476, 481866, 481868, 482067, 482138, 482109, 482110, 482111, 482112, 482113, 482114, 482139, 482233, 482234, 482235)
PRICE=50
CATEGORY=37 # Native consume/dyeing category.
POLICY='owner-approved-20-permanent-palettes-50ED-20261118'
EXPECTED={
 481213:('染发调色板（日常）',True,1,'11059af5a8cad6277d443eba7a2a18340522ee40df044dc1c7bcf082f708a65a'),
 481214:('染发调色板（自然）',True,2,'f0249463bdd3ab2acfdf3539640b1184284fd6762cdf0e2cf1af6c3eacfc8a1d'),
 481239:('染发调色板（紫色心情）',True,4,'c241d7e85040ee32d5ec0e8fdcda32e95e37eab0e3cadee91c0a3870ef1e1660'),
 481283:('染发调色板（糖果情缘）',True,5,'2cab81c20f67d68551eb0c059ce0763f784ba236a74ecf6829cdd464a1a9c6ee'),
 481341:('染发调色板（极光夜曲）',True,8,'45de3d290892ddaafa45cefefbb2ee2b047001535d4bb5e4f03cd97e194e7f1e'),
 481476:('染发调色板（热带日落）',True,9,'bf20cc3b9d1812b7a93ba6a0c9c2a7e79e7fe61b837279b67d11dd689f23aaf5'),
 481866:('染发调色板（波光粼粼）',True,10,'acb6cd43ed012ad4581159b749155ccb39301caf6de0c4fe0a115d3e72e65756'),
 481868:('染发调色板（刻奇原宿）',True,11,'fd0ca3879d6b1add8549a0d0cb36d0d0ae90f9870758ef02b13319c9999e247c'),
 482067:('染发调色板（轻声细雨）',True,12,'13812fe1f121b7dc05c17582d00e7ba986a835a076da5af57c356cdf7fe34a64'),
 482138:('染发调色板（艾里奥斯快餐店）',True,14,'c858178870335454261c3ef9a4ead9601942f41088a5d41fff7630e5b1c84c17'),
 482109:('时装调色板（日常）',False,1,'f3e52c140bace077d100512088538791e3a9ecdd35a817e9377c4cbbe1189693'),
 482110:('时装调色板（自然）',False,2,'fe55644556c984e76ad0e1af5eb523698c9ae3a4ea3c6813428978bfa8b8a0f5'),
 482111:('时装调色板（波光粼粼）',False,10,'7567e4dff70e921c1354abf694174e1e568075ff4963dd445dcd674de473e2bc'),
 482112:('时装调色板（热带日落）',False,9,'296e36ee83497aa05336005545c645ce02070568545734ad74b90dcfec8efe08'),
 482113:('时装调色板（刻奇原宿）',False,11,'6d6e38822f1a93940e316dc6fb691328d5aadcb12dd59bcac49e63893ee43e20'),
 482114:('时装调色板（轻声细雨）',False,12,'4e7f26c1ed55efe190a664e026b20d61651e6388b27c47d46e5efc47b2a9076f'),
 482139:('时装调色板（艾里奥斯快餐店）',False,14,'3e20fdcdeac22118aa1b23b864c59e50b5ed733ae7c49aab674bdaebce6b583b'),
 482233:('时装调色板（紫色心情）',False,4,'fe3bc199a0714dfa54f3b33a4634c9f9c0e1dcb6d0dac0c9a960ed7f7b4a0810'),
 482234:('时装调色板（糖果情缘）',False,5,'6babb3b4255d1805d95df8b3b89908b38ac6fbf78991c06d19d6494a31f2595a'),
 482235:('时装调色板（极光夜曲）',False,8,'93a09ff6649c31d7805da523a312e575b4c8d6c5a1670d286a9746ae0a132f3d'),
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
            raise ValueError('Palette current native source mismatch')
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
