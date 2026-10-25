"""21FFE00 kind 1C6 -> 227D980: vector<pair<UID,i32 template>>, vector<i32>.

The second list's additional semantics are pending and it stays empty. This is
an expiration removal notification, not an acquisition delta or a move ACK.
"""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.inventory_items import validate_item


def notice(items):
    if not isinstance(items,list) or not 1<=len(items)<=2000:raise ValueError('Expiration list bound')
    items=[validate_item(i) for i in items]
    if any('expires_at' not in i for i in items) or len({i['uid'] for i in items})!=len(items):raise ValueError('Expiration identities')
    return Event(0x201,kind=0x1c6,payload=struct.pack('>I',len(items))+b''.join(struct.pack('>Qi',i['uid'],i['template']) for i in items)+bytes(4))
