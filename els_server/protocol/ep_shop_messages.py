"""Original A5F request / A60 inventory-purchase reply, never ED purchase."""
import struct
from els_server.domain.ep_points import validate as ep_balance
from els_server.domain.inventory_items import inventory_payload
from els_server.protocol.protocol_codec import Event


def purchase_request(payload):
    if type(payload) is not bytes or len(payload)!=8:
        raise ValueError('Invalid EP purchase size')
    template,quantity=struct.unpack('>ii',payload)
    if not 1<=template<2**31 or not 1<=quantity<=10000:
        raise ValueError('Invalid EP product or quantity')
    return template,quantity


def purchase_ack(result,ep,counts,items):
    ep_balance(ep)
    if type(result) is not int or not -2**31<=result<2**31:
        raise ValueError('Invalid EP purchase result')
    if type(counts) is not dict or any(type(k) is not int or not 1<=k<2**31
        or type(v) is not int or not 0<=v<2**31 for k,v in counts.items()):
        raise ValueError('Invalid EP purchase counts')
    body=struct.pack('>iQI',result,ep,len(counts))
    body+=b''.join(struct.pack('>ii',key,counts[key]) for key in sorted(counts))
    return Event(0x201,kind=0xa60,payload=body+inventory_payload(items))


# Current packed39 consumer contract. Category/order/group are explicitly this
# server's display profile, not original retail catalogue values. Fields8/27
# use the separately reviewed canonical-zero compatibility contract.
_PROFILES={723602:(100,1,1),723603:(10,1,2),723604:(5,1,3),710022:(15,100,4)}
_LIMITED=frozenset((723602,723603,723604))


def catalogue_records(offers):
    from els_server.domain.ep_shop import Offer
    if type(offers) is not tuple or len(offers)>4 or any(type(o) is not Offer for o in offers):
        raise ValueError('Unqualified EP goods catalogue')
    if len({o.template for o in offers})!=len(offers):raise ValueError('Duplicate EP goods')
    rows=[]
    for offer in sorted(offers,key=lambda o:o.template):
        profile=_PROFILES.get(offer.template)
        if profile is None or (offer.unit_price,offer.unit_quantity)!=profile[:2]:
            raise ValueError('EP goods source profile mismatch')
        limit=offer.limit
        if offer.template in _LIMITED:
            if limit is None or limit.scope!='account' or limit.maximum!=1:
                raise ValueError('EP account weekly display profile mismatch')
            maximum,scope=1,1
        else:
            if limit is not None:raise ValueError('Manual potion must use explicit unlimited policy')
            maximum,scope=0,0
        # value0,category,opaque8,display_count,EPprice,max,scope26,
        # opaque27,feature-group31,display-rank35. Current Enum consume=1.
        value=struct.pack('>iiHiQiBiii',offer.template,1,0,offer.unit_quantity,
                          offer.unit_price,maximum,scope,0,0,profile[2])
        rows.append(struct.pack('>i',offer.template)+value)
    return struct.pack('>I',len(rows))+b''.join(rows)


def _snapshot_row(template,count):
    # Root-reviewed bounded native-observation compatibility input. This tail
    # is neither this server's weekly reset nor a retail/cross-host time claim.
    return 0,946656000


def count_snapshot(counts,*,row_factory=None):
    if type(counts) is not dict or any(type(k) is not int or k not in _LIMITED
        or type(v) is not int or not 0<=v<2**31 for k,v in counts.items()):
        raise ValueError('Invalid EP complete count projection')
    factory=_snapshot_row if row_factory is None else row_factory
    rows=[]
    for template,count in sorted(counts.items()):
        opaque=factory(template,count)
        if (type(opaque) is not tuple or len(opaque)!=2 or type(opaque[0]) is not int
            or not -2**31<=opaque[0]<2**31 or type(opaque[1]) is not int or not 0<=opaque[1]<2**64):
            raise ValueError('Invalid EP count row compatibility input')
        rows.append(struct.pack('>iiiQ',template,opaque[0],count,opaque[1]))
    # A5E replaces manager+30 wholesale. No result, UID, scope or partial merge.
    return Event(0x201,kind=0xa5e,payload=struct.pack('>I',len(rows))+b''.join(rows))
