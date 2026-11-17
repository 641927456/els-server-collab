"""Original housing option, invitation and room-member packet layouts."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring
from els_server.protocol.housing_messages import _encode
from els_server.protocol.housing_population_messages import member
from els_server.protocol.social_messages import town_movement


def text_request(payload, *, option=False):
    if type(payload) is not bytes or len(payload) < 4:
        raise ValueError('Housing native string request')
    size, = struct.unpack_from('>I', payload)
    if size % 2 or not 0 < size <= 65534 or len(payload) != 4 + size + int(option):
        raise ValueError('Housing native string width')
    text = payload[4:4+size].decode('utf-16le', errors='strict')
    if '\x00' in text:
        raise ValueError('Housing native string terminator')
    if not option:
        return text
    flag = payload[-1]
    if flag not in (0, 1):
        raise ValueError('Housing native public checkbox')
    return text, bool(flag)


def options_ack(result=0):
    return Event(0x201, kind=0x93c, payload=struct.pack('>i', result))


def options_notice(value):
    schema = (('name', 'str'), ('floors', ('map', 'i', ('tuple', 'i', 'i'))),
              ('presets', 'i'), ('public', 'bool'), ('opaque', 'Q'))
    row = dict(name=value['0ba'], floors=value['0da'], presets=value['0ea'],
               public=value['0ee'], opaque=value['0ef'])
    return Event(0x201, kind=0x93d, payload=_encode(schema, row))


def invite_ack(name='', target=0, *, result=0):
    return Event(0x201, kind=0x931, payload=struct.pack('>i', result) + wstring(name) + struct.pack('>Q', target))


def invitation_list(rows):
    # 2C281A0 reads Q, string, string, byte occupancy, bool availability.
    data = struct.pack('>iI', 0 if rows else 2428, len(rows))
    for uid, owner_name, room_name, occupancy, available in rows:
        data += struct.pack('>Q', uid) + wstring(owner_name) + wstring(room_name)
        data += struct.pack('>B?', occupancy, available)
    return Event(0x201, kind=0x933, payload=data)


def added(row, roster):
    body = member(*row) + struct.pack('>I', len(roster))
    body += b''.join(struct.pack('>Q', uid) for uid in roster)
    return Event(0x201, kind=0x929, payload=body)


def removed(uid, roster):
    host = roster[0] if roster else 0
    body = struct.pack('>QIQI', uid, 0, host, len(roster))
    return Event(0x201, kind=0x92a, payload=body + b''.join(struct.pack('>Q', value) for value in roster))


def population(rows, *, result=0):
    return Event(0x201, kind=0x92f, payload=struct.pack('>iI', result, len(rows)) + b''.join(member(*row) for row in rows) + bytes(12))


def moved(uid, payload):
    return Event(0x201, kind=0x92c, payload=town_movement(uid, payload).payload)


def layout_notice(layout, selected):
    from els_server.protocol.housing_layout_messages import LAYOUT, encode
    return Event(0x201, kind=0x937, payload=encode(LAYOUT, layout) + struct.pack('>i', selected))
