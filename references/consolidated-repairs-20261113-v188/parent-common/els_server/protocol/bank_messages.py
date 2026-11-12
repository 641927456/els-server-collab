"""Native 551/552 bank transfers and 372/373 bank ordering."""
import struct
from els_server.domain.inventory_items import item_body
from els_server.domain.fashion_state import record,empty_record


def transfer_request(payload):
    if not isinstance(payload,bytes) or len(payload)!=26:
        raise ValueError('Bank transfer size')
    sg,ss,dg,ds,quantity,context,template=struct.unpack('>BiBiiQi',payload)
    if (sg,ss)==(dg,ds) or not {8,16}&{sg,dg} or quantity<=0 or template<=0:
        raise ValueError('Unsupported bank transfer')
    if not 0<=ss<392 or not 0<=ds<392:
        raise ValueError('Bank transfer slot bound')
    return (sg,ss),(dg,ds),quantity,context,template


def bank_record(entry):
    group,slot=entry['position']
    if group not in (8,16) or not 0<=slot<48:
        raise ValueError('Bank wire position')
    item=entry['item']
    return struct.pack('>QBh',item['uid'],group,slot)+item_body(item)+bytes(9)


def transfer_ack(changes=(),result=0):
    return struct.pack('>I',len(changes))+b''.join(
        empty_record(*p) if item is None else bank_record(dict(position=p,item=item)) if p[0] in (8,16) else record(item)
        for p,item in changes)+struct.pack('>i',result)


def sort_ack(group=8,removed=(),entries=(),result=0):
    # 2394F70: group, vector<UID>, result, vector<inventory row>.
    return (struct.pack('>iI',group,len(removed))+b''.join(struct.pack('>Q',u) for u in removed)
        +struct.pack('>iI',result,len(entries))+b''.join(bank_record(e) for e in entries))


def restore_map(normal,bank):
    from els_server.domain.inventory_items import inventory_restore_map
    base=inventory_restore_map(normal)
    count=struct.unpack_from('>I',base)[0]
    if {i['uid'] for i in normal}&{e['item']['uid'] for e in bank}:
        raise ValueError('Bank and inventory UID collision')
    if len({e['item']['uid'] for e in bank})!=len(bank) or len({tuple(e['position']) for e in bank})!=len(bank):
        raise ValueError('Duplicate bank UID or position')
    return struct.pack('>I',count+len(bank))+base[4:]+b''.join(
        struct.pack('>Q',e['item']['uid'])+bank_record(e) for e in bank)


def contents_ack(entries=(),ed=None,result=0):
    # C4FAA0 (26B): map<UID,row>. C4FB60 (550): result, map, bank ED.
    body=struct.pack('>I',len(entries))+b''.join(
        struct.pack('>Q',e['item']['uid'])+bank_record(e) for e in entries)
    return body if ed is None else struct.pack('>i',result)+body+struct.pack('>Q',ed)


def quote_ack(group,cost=0,result=0):
    # 478 adds an i32 after result/ED; this native consumer ignores it.
    return struct.pack('>iQ',result,cost)+(bytes(4) if group==8 else b'')


def expansion_ack(group,ed=0,delta=0,result=0):
    # 234B840 (476) and 23962B0 (54E): result, absolute ED, map deltas;
    # only 476 has the trailing i32. A replay MUST send an empty delta map.
    values={group:delta} if delta else {}
    return (struct.pack('>iQI',result,ed,len(values))+
        b''.join(struct.pack('>ii',g,n) for g,n in values.items())+
        (bytes(4) if group==8 else b''))


def money_request(payload):
    # 2431430: bool at packed +0, unsigned amount at +1.
    if not isinstance(payload,bytes) or len(payload)!=9 or payload[0] not in (0,1):
        raise ValueError('Invalid shared ED request')
    deposit,amount=struct.unpack('>BQ',payload)
    if not 1<=amount<=70_000_000_000:raise ValueError('Invalid shared ED amount')
    return bool(deposit),amount


def money_ack(deposit,bank_ed=0,character_ed=0,result=0):
    # 2395230: result:i32, direction:bool, absolute bank ED:u64, player ED:u64.
    if type(deposit) is not bool or any(type(n) is not int or not 0<=n<2**63 for n in (bank_ed,character_ed)):
        raise ValueError('Invalid shared ED response')
    return struct.pack('>iBQQ',result,deposit,bank_ed,character_ed)
