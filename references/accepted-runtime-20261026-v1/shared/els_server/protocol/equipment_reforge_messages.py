"""Original8D5/8D6 forging and distinct8D9/8DA life restoration shapes."""
import struct
from els_server.protocol.protocol_codec import Event

def uid(value):
    if type(value) is not int or not 0<value<2**63:raise ValueError('Reforge instance UID')
    return value

def request(payload,*,restoration=False):
    if not isinstance(payload,bytes) or len(payload)!=(20 if restoration else 14):raise ValueError('Reforge request length')
    if restoration:
        target,material,quantity=struct.unpack('>QQi',payload);uid(target);uid(material)
        if target==material or not 1<=quantity<=100:raise ValueError('Reforge restore identities/quantity')
        return target,material,quantity
    target,selected,flag1,flag2=struct.unpack('>QiBB',payload);uid(target)
    # Original full-guarantee UI sends template0. SQL checks the real gauge;
    # neither client flag grants free attempts or admits ED-free tickets.
    if selected<0 or flag1 or flag2 not in (0,1):raise ValueError('Reforge material or unsupported mode')
    return (target,selected,True) if flag2 else (target,selected)

def changes_wire(changes):
    from els_server.domain.fashion_state import record,empty_record
    rows=list(changes)
    if len(rows)>72 or len({tuple(p) for p,i in rows})!=len(rows):raise ValueError('Reforge changed positions')
    return struct.pack('>I',len(rows))+b''.join(empty_record(*p) if item is None else record(item) for p,item in rows)

def acknowledge(target=0,ed=0,level=0,status=0,changes=(),result=0):
    if any(type(v) is not int or not 0<=v<2**63 for v in (target,ed)) or type(level) is not int or not 0<=level<=21 or status not in (0,1,2) or type(status) is not int:raise ValueError('Reforge acknowledgement fields')
    if type(result) is not int or not -2**31<=result<2**31:raise ValueError('Reforge result')
    return Event(0x201,kind=0x8d6,payload=struct.pack('>iQQii',result,ed,target,level,status)+changes_wire(changes)+bytes(4))

def restore_ack(changes=(),result=0):
    if type(result) is not int or not -2**31<=result<2**31:raise ValueError('Reforge restore result')
    return Event(0x201,kind=0x8da,payload=struct.pack('>i',result)+changes_wire(changes))
