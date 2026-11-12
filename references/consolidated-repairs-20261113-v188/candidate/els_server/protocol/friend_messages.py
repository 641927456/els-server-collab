"""Current 248..262 friendship packets, verified against c8815e00 readers."""
import struct
from els_server.protocol.local_messages import i32, u32, wstring
from els_server.protocol.protocol_codec import Event
from els_server.protocol.guild_membership_messages import _string

REQUESTS = frozenset((0x248, 0x24b, 0x24e, 0x251, 0x254, 0x257,
                      0x25a, 0x25c, 0x25e, 0x260))


def request(kind, payload):
    if type(payload) is not bytes or len(payload) > 16400:
        raise ValueError('Friend request body')
    if kind == 0x248:
        name, offset = _string(payload, 0)
        message, offset = _string(payload, offset)
        result = dict(name=name, message=message)
    elif kind in (0x24b, 0x24e, 0x251, 0x254, 0x257):
        if len(payload) != 8:
            raise ValueError('Friend target body')
        result = dict(target=struct.unpack('>Q', payload)[0])
        offset = 8
    elif kind == 0x25a:
        if len(payload) != 12:
            raise ValueError('Friend move body')
        target, group = struct.unpack('>Qi', payload)
        result, offset = dict(target=target, group=group), 12
    elif kind == 0x25c:
        name, offset = _string(payload, 0)
        result = dict(name=name)
    elif kind == 0x25e:
        if len(payload) < 8:
            raise ValueError('Friend group rename body')
        group = struct.unpack_from('>i', payload)[0]
        name, offset = _string(payload, 4)
        result = dict(group=group, name=name)
    elif kind == 0x260:
        if len(payload) != 4:
            raise ValueError('Friend group deletion body')
        result, offset = dict(group=struct.unpack('>i', payload)[0]), 4
    else:
        raise ValueError('Unknown friend request')
    if offset != len(payload):
        raise ValueError('Friend trailing bytes')
    return result


def event(kind, body):
    return Event(0x201, kind=kind, payload=body)


def acknowledgement(kind, *, result=0, target=0, name='', group=0):
    if kind == 0x248:
        body = i32((21) if result == -1 else result) + struct.pack('>Q', target) + wstring(name)
    elif kind in (0x24b, 0x24e, 0x251, 0x254, 0x257):
        body = i32((21) if result == -1 else result) + struct.pack('>Q', target)
    elif kind == 0x25a:
        body = i32((21) if result == -1 else result) + struct.pack('>Qi', target, group)
    elif kind in (0x25c, 0x25e):
        body = i32((21) if result == -1 else result) + i32(group) + wstring(name)
    elif kind == 0x260:
        body = i32((21) if result == -1 else result) + i32(group)
    else:
        raise ValueError('Unknown friend reply')
    return event(kind + 1, body)


def invitation(uid, name, message):
    # 31E3240: Q, nickname, message, without a result prefix.
    return event(0x24a, struct.pack('>Q', uid) + wstring(name) + wstring(message))


def notification(kind, uid, name=''):
    body = struct.pack('>Q', uid)
    if kind == 0x250:
        body += wstring(name)
    return event(kind, body)


def info(row):
    # DCDCB0: UID, name, i32 group, status/position/unit bytes, class u16,
    # native level i32, rank i8, guild name, two i32 locations, last bool.
    return (struct.pack('>Q', row['uid']) + wstring(row['name'])
            + struct.pack('>iBBBHib', row['group'], row['status'], row['online'],
                          row['unit_type'], row['unit_class'], row['level'], row['rank'])
            + wstring(row['guild_name'])
            + struct.pack('>iiB', row['channel'], row['map'], row['context_flag']))


def info_map(rows):
    return u32(len(rows)) + b''.join(struct.pack('>Q', row['uid']) + info(row)
                                    for row in sorted(rows, key=lambda row: row['uid']))


def messenger(value):
    # DA37C0 +8F/+9F/+AF: friend map, group map<i32,wstring>, pending vector.
    result = info_map(value['friends'])
    groups = value['groups']
    result += u32(len(groups)) + b''.join(i32(key) + wstring(name)
                                          for key, name in sorted(groups.items()))
    pending = value['pending']
    result += u32(len(pending))
    for row in pending:
        result += (struct.pack('>Q', row['uid']) + wstring(row['name']) + b'\0'
                   + wstring(row['message']) + wstring(row['date']))
    return result


def restore(message, value, *, mentor_partners=()):
    # DA37C0/DD90A0: the first vector after the27-byte prefix restores
    # PublicInfo + supplementary string. Build it and the existing messenger
    # together from this empty source, preserving every other field.
    if message.event_id != 0x201 or message.kind != 0x2f:
        return message
    if (len(message.payload) < 55 or message.payload[27:31] != bytes(4)
            or message.payload[43:55] != bytes(12)):
        raise ValueError('Friend initialization source layout changed')
    from els_server.protocol.mentor_messages import public_info
    partners=u32(len(mentor_partners))+b''.join(public_info(row)+wstring('')for row in mentor_partners)
    return event(0x2f, message.payload[:27]+partners+message.payload[31:43]+messenger(value)+message.payload[55:])


def positions(rows):
    return event(0x262, info_map(rows))
