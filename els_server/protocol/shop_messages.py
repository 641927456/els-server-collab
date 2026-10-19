"""Current-build native shop messages.

The normal cash catalog remains empty; the independent ED catalog and purchase
use 80D/80E and 80F/810, verified against 313A890 and 1C8F6D0.
"""
import struct
from dataclasses import dataclass
from els_server.protocol.protocol_codec import Event

def availability_notice(enabled=True):
    if type(enabled) is not bool:
        raise ValueError('Shop availability must be boolean')
    return Event(0x201,kind=0x369,payload=bytes([enabled]))

def catalog_request(payload):
    # Original 31C27A0 serializes the signed category/version selector at +4B4.
    if payload!=struct.pack('>i',1):
        raise ValueError('Unsupported native shop catalog selector')

def empty_catalog_ack(accepted=True):
    if type(accepted) is not bool:
        raise ValueError('Shop catalog result must be boolean')
    # 3113D50: bool, product vector, four maps, int set, two ints, int vector.
    # All containers intentionally empty until individual product fields
    # have both native-consumer and transaction evidence.
    return Event(0x201,kind=0xd79,payload=bytes([accepted])+bytes(36))


def empty_cart_ack():
    """Empty native 1F2 wish-list/shopping-cart map.

    1C4D500 reads u32 count and pairs of signed i32 into UI+3B8.
    1C71230 refreshes slot types 15/21 (CHOICED), not deposit type 14.
    ED purchases enter the character bag directly via 810.
    """
    return Event(0x201,kind=0x1f2,payload=bytes(4))


def empty_deposit_ack(result=0):
    """D7B bought-item page, empty because this profile sells direct-bag ED items.

    23D2740 requests page capacity21 + page1. 23D6A80 parses i32 result,
    two structured vectors and two int vectors, then 23D2500 refreshes the
    actual cashShop.bought_item_slot/page controls (slot type14).
    """
    return Event(0x201,kind=0xd7b,payload=struct.pack('>i',result)+bytes(16))


@dataclass(frozen=True)
class PurchaseRequest:
    products: tuple[tuple[int,int], ...]
    mode: bool
    option: int


def purchase_request(payload):
    """Decode 1DD only; no purchase authorization or persistence here.

    20F4F80/2BDDCF0: u32 count, (u32 SKU,u16 quantity)*, bool, i32.
    The final mode/option semantics still require the native UI witnesses.
    Limits below are this isolated server's bounds, not retail limits.
    """
    if len(payload)<9:
        raise ValueError('Truncated shop purchase')
    count,=struct.unpack_from('>I',payload)
    if not 1<=count<=100 or len(payload)!=9+6*count:
        raise ValueError('Invalid shop purchase length or count')
    products=tuple(struct.unpack_from('>IH',payload,4+6*i) for i in range(count))
    if any(sku==0 or quantity==0 for sku,quantity in products):
        raise ValueError('Empty shop SKU or quantity')
    if len({sku for sku,_ in products})!=count:
        raise ValueError('Duplicate shop SKU')
    mode=payload[4+6*count]
    if mode not in (0,1):
        raise ValueError('Invalid shop purchase mode')
    option,=struct.unpack_from('>i',payload,5+6*count)
    return PurchaseRequest(products,bool(mode),option)


def purchase_ack(result,products=(),mode=False,detail_kind=0,detail=0,flag=False):
    """Native 1DE wire layout from 20E9D50/2BDDDC0; not a grant operation."""
    if type(mode) is not bool or type(flag) is not bool:
        raise ValueError('Shop ACK flags must be boolean')
    if len(products)>100:
        raise ValueError('Too many shop ACK products')
    rows=b''.join(struct.pack('>IH',sku,quantity) for sku,quantity in products)
    payload=struct.pack('>iI',result,len(products))+rows+struct.pack('>BBiB',mode,detail_kind,detail,flag)
    return Event(0x201,kind=0x1de,payload=payload)


def ed_catalog_ack(products):
    # 313A890 / 2B4F3C0: completed bool, vector of seven 32-bit fields.
    # +8 is real subcategory (69D230 / CashShopCategory.lua), not currency.
    rows=b''.join(struct.pack('>Iiiiiii',p['sku'],p['template'],p['category'],
                             p['price'],0,p['quantity'],0) for p in products)
    return Event(0x201,kind=0x80e,payload=b'\1'+struct.pack('>I',len(products))+rows)


def ed_purchase_request(payload):
    # Original 2113130: only the SKU/quantity vector; no mode or coupon tail.
    return purchase_request(payload+b'\0'+struct.pack('>i',-1)).products


def ed_purchase_ack(result,items,ed):
    # 1C8F6D0: result, unused i32, DD46E0 item vector, u64 remaining ED.
    from els_server.domain.inventory_items import inventory_payload
    return Event(0x201,kind=0x810,payload=struct.pack('>ii',result,0)+inventory_payload(items)+struct.pack('>Q',ed))
