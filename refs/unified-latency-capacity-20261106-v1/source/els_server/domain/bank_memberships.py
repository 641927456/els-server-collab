"""Original immediate bank memberships, offered by the existing local ED shop.

Product IDs/target tiers come from 1985AC0 and item.kim descriptions. This
profile has an ED storefront, not a cash balance. Its prices use the matching
ED upgrade costs; the 8->48 credit guarantee costs the sum of those steps.
"""
import struct
from els_server.game_data import client_data
from els_server.domain.bank_rules import TIERS,ED_COSTS
from els_server.protocol.protocol_codec import Event

PRODUCTS={213460:(8,8,16),213470:(8,16,24),213480:(8,24,32),
          213490:(8,32,40),213500:(8,40,48),
          283132:(16,8,16),283133:(16,16,24),283134:(16,24,32),
          283135:(16,32,40),283136:(16,40,48),283131:(16,8,48)}


def offers():
    result=[]
    for template,(group,before,after) in PRODUCTS.items():
        item=client_data().item(template)
        if item['item_type']!=7 or item['metadata']!=0:raise ValueError('Bank membership original definition mismatch')
        price=sum(ED_COSTS[group][TIERS.index(before):TIERS.index(after)])
        result.append(dict(sku=1200000000+template,template=template,name=item['name'],category=41,price=price,quantity=1))
    return tuple(result)


def notice(before,after):
    old=(before or {}).get('bank_capacities',{});new=(after or {}).get('bank_capacities',{})
    delta={g:new[g]-old.get(g,8) for g in (8,16) if g in new and new[g]!=old.get(g,8)}
    if any(n<=0 or n%8 or n>40 for n in delta.values()):raise ValueError('Invalid membership capacity delta')
    if not delta:return None
    return Event(0x201,kind=0x26c,payload=struct.pack('>I',len(delta))+
        b''.join(struct.pack('>ii',g,n) for g,n in delta.items())+bytes(12))
