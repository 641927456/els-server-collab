"""Verified native bag groups, eight-slot products and bounded wire records.

The existing 36-slot starting allowance is local policy, not an official base.
392 is the ordinary/life purchase ceiling (2255C80/23D3AE0). With the
preserved local base, eight-slot purchases stop at 388. Avatar and ice avatar
pages are the same eight-slot ladder but reach the original 840/1120 ceilings.
"""
import struct
from els_server.protocol.protocol_codec import Event

LOCAL_BASE=36
NATIVE_LIMIT=392
PRODUCT_GROUPS={200751:1,200752:2,200753:6,200754:3,200755:5,200756:4,135964:21}
# Original 2255C80 switch: 105/140 rows of eight for avatar/ice avatar. These
# are purchase ceilings for the same eight-slot primitive, not a free grant.
FASHION_LIMITS={7:840,27:1120}
# This build ships no coupon for the housing or costume tabs, yet their canvases
# draw the same locked row and "+" as an ordinary bag. Leaving them unpriced is
# what makes those buttons look dead, so they are priced locally instead.
LOCAL_PRODUCTS={'local-avatar':7,'local-furniture':25,'local-ice-avatar':27}
LOCAL_PRICES={'local-avatar':50,'local-furniture':50,'local-ice-avatar':50}
EXPANDABLE=frozenset(PRODUCT_GROUPS.values())|frozenset(LOCAL_PRODUCTS.values())
BAG_GROUPS=(1,2,3,4,5,6,7,21,25,27)
QUICK_SLOT_GROUP=11
# Preserve this local profile's existing six visible item shortcuts explicitly.
# Native 3059AD0 accepts 3/6 and clamps its constructor's placeholder 67 to 6.
# This is a local allowance, not evidence of the retail starting entitlement.
LOCAL_QUICK_SLOTS=6

def limit(group):
    return FASHION_LIMITS.get(group,NATIVE_LIMIT)

def wire_limit(group):
    if group==QUICK_SLOT_GROUP:return LOCAL_QUICK_SLOTS
    return FASHION_LIMITS.get(group,NATIVE_LIMIT if group in EXPANDABLE else LOCAL_BASE)

def capacities(character=None):
    result={g:LOCAL_BASE for g in BAG_GROUPS}
    result[QUICK_SLOT_GROUP]=LOCAL_QUICK_SLOTS
    for key,value in (character or {}).get('bag_capacities',{}).items():
        group=int(key)
        ceiling=limit(group)
        # 840 and 1120 are the native ceilings; every step below them is the
        # same eight-slot purchase as the ordinary tabs.
        valid=(group in EXPANDABLE and type(value) is int and LOCAL_BASE<=value<=ceiling
               and ((value-LOCAL_BASE)%8==0 or (group in FASHION_LIMITS and value==ceiling)))
        if type(value) is not int or not valid:
            raise ValueError('Invalid persisted bag capacity')
        result[group]=value
    return result

def capacity_map(character=None):
    # 2A/DA3370+5A1 -> C62740 map<int,int> -> 8695F0 absolute capacities.
    values=capacities(character)
    for group,value in (character or {}).get('bank_capacities',{}).items():
        group=int(group)
        if group not in (8,16) or type(value) is not int or value not in (8,16,24,32,40,48):raise ValueError('Invalid bank allowance')
        values[group]=value
    return struct.pack('>I',len(values))+b''.join(struct.pack('>ii',g,n) for g,n in sorted(values.items()))

def expansion_notice(before,after):
    # 201/26C -> 21FFE00 -> 22770C0 adds map values. Trailing i32/u64 are
    # parsed but unused in this build. Do not resend a delta on receipt replay.
    old,new=capacities(before),capacities(after)
    changes={g:new[g]-old[g] for g in BAG_GROUPS if new[g]!=old[g]}
    if any(g not in EXPANDABLE or n<=0 or n%8 for g,n in changes.items()):raise ValueError('Invalid expansion delta')
    if not changes:return None
    body=struct.pack('>I',len(changes))+b''.join(struct.pack('>ii',g,n) for g,n in sorted(changes.items()))+bytes(12)
    return Event(0x201,kind=0x26c,payload=body)


def additional_offers():
    # The six old products retain their pinned catalog entries. Life is also
    # explicitly listed in the original CashShopBuyPopUpData expansion family.
    from els_server.game_data import client_data
    item=client_data().item(135964)
    if item['item_type']!=7 or item['flags4']!=0x401002:raise ValueError('Life expansion definition mismatch')
    return (dict(sku=1200135964,template=135964,name=item['name'],category=41,price=50,quantity=1),)
