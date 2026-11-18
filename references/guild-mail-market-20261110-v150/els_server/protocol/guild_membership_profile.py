"""Current native membership, rank, skill-page and fountain profile codecs."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.equipment_chip_messages import changes_wire


def _string(value):
    if type(value) is not str or '\0' in value:
        raise ValueError('Guild profile string')
    raw = value.encode('utf-16le', errors='strict')
    if len(raw) > 8192:
        raise ValueError('Guild profile string bound')
    return struct.pack('>I', len(raw)) + raw


def _integer(value, bits, signed=False):
    low = -(2**(bits-1)) if signed else 0
    high = 2**(bits-1)-1 if signed else 2**bits-1
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Guild profile integer bound')
    return value.to_bytes(bits//8, 'big', signed=signed)


def basic(profile, *, empty=False):
    fields = ('id', 'name', 'max_members', 'level', 'experience', 'message',
              'founding_day', '6b', '6f', '73', '77', '78', '7c', '7d',
              '81', '85', '89', '8a', 'aa', 'ca')
    if set(profile) != set(fields):
        raise ValueError('Incomplete or extended guild basic profile')
    if (profile['77'] not in (False, True)
            or (not empty and (profile['id'] <= 0 or not profile['name']))
            or (empty and any(v not in (0,False,'') for v in profile.values()))):
        raise ValueError('Guild basic identity/boolean')
    return b''.join((
        _integer(profile['id'], 32, True), _string(profile['name']),
        _integer(profile['max_members'], 16), _integer(profile['level'], 8),
        _integer(profile['experience'], 32, True), _string(profile['message']),
        _string(profile['founding_day']),
        *(_integer(profile[k], 32, True) for k in ('6b','6f','73')),
        bytes((int(profile['77']),)), _integer(profile['78'], 32, True),
        _integer(profile['7c'], 8),
        *(_integer(profile[k], 32, True) for k in ('7d','81','85')),
        _integer(profile['89'], 8), _string(profile['8a']), _string(profile['aa']),
        _integer(profile['ca'], 64)))


def full(profile):
    from els_server.domain.guild_bank_rules import permissions_wire
    required = {'basic','master_name','members','pages','active_page',
                '11b','133','14b','153','163','173','183','193','1b3','1d3','1db'}
    if set(profile) != required:
        raise ValueError('Incomplete or extended guild full profile')
    # Nonempty modern feature state needs its own proven serializer/producer.
    # Callers must explicitly provide each collection, not omit defaults.
    if any(profile[k] != () for k in ('11b','133','153')):
        raise ValueError('Unsupported acquired modern guild extension')
    members = profile['members']
    if (type(members) is not tuple or not 1 <= len(members) <= profile['basic']['max_members']
            or len(set(members)) != len(members)):
        raise ValueError('Guild full member vector')
    pages=profile['pages']
    if profile['active_page']not in pages:raise ValueError('Guild selected page')
    page_bytes=pages_wire(pages)
    return (basic(profile['basic']) + _string(profile['master_name'])
            + _integer(len(members), 32) + b''.join(_integer(uid, 64) for uid in members)
            + page_bytes
            + _integer(profile['active_page'], 8)
            + bytes(8) + _integer(profile['14b'], 64) + bytes(4) + permissions_wire(profile['163'])
            + emblems_wire(profile['173']) + skins_wire(profile['183'])
            + _string(profile['193']) + _string(profile['1b3'])
            + _integer(profile['1d3'], 64) + struct.pack('>I',len(profile['1db']))+b''.join(struct.pack('>iB',socket,count)for socket,count in profile['1db']))


def emblems_wire(rows):
    from els_server.protocol.guild_emblem_messages import collection
    return collection(rows)


def skins_wire(rows):
    return struct.pack('>I',len(rows))+b''.join(struct.pack('>ii?',*row)for row in rows)


def pages_wire(pages):
    if type(pages) is not dict or not 1 <= len(pages) <= 3:
        raise ValueError('Guild full skill pages')
    page_bytes = []
    for index, page in sorted(pages.items()):
        if index not in (1, 2, 3) or set(page) != {'skills','points','cash_points','max_cash_points','expiry','alias'}:
            raise ValueError('Guild page identity/fields')
        skills=page['skills']
        if len({row[0]for row in skills})!=len(skills):raise ValueError('Duplicate guild skill')
        # DB5EF0: signed short skill ID, level byte, level paid with bonus GSP byte.
        skill_bytes=b''.join(struct.pack('>hBB',identity,rank,cash_rank)for identity,rank,cash_rank in skills)
        page_bytes.append(_integer(index, 8) + _integer(len(skills),32)+skill_bytes + b''.join(
            _integer(page[k], 32, True) for k in ('points','cash_points','max_cash_points'))
            + _string(page['expiry']) + _string(page['alias']))
    return _integer(len(pages),32)+b''.join(page_bytes)


def create_ack(profile, changes):
    return Event(0x201, kind=0x277,
                 payload=bytes(4)+basic(profile)+changes_wire(changes))


def full_notification(profile, joined=False):
    return Event(0x201, kind=0x28b if joined else 0x278, payload=full(profile))


def invite_ack(recipient):
    return Event(0x201, kind=0x286, payload=bytes(4)+_string(recipient))


def invitation(profile, inviter, rules):
    # Current287: basic, inviter, auto-join boolean, guild rules. Native
    # invitation requires explicit recipient confirmation, so auto-join=false.
    return Event(0x201, kind=0x287,
                 payload=basic(profile)+_string(inviter)+b'\0'+_string(rules))


def accepted_ack():
    return Event(0x201, kind=0x289, payload=bytes(4))


def failed(kind):
    if kind == 0x276:
        p = {k:0 for k in ('id','max_members','level','experience','6b','6f',
                           '73','77','78','7c','7d','81','85','89','ca')}
        p.update({k:'' for k in ('name','message','founding_day','8a','aa')})
        return Event(0x201,kind=0x277,
                     payload=_integer(-1,32,True)+basic(p,empty=True)+changes_wire(()))
    if kind == 0x285:
        return Event(0x201,kind=0x286,payload=_integer(-1,32,True)+_string(''))
    if kind == 0x288:
        return Event(0x201,kind=0x289,payload=_integer(-1,32,True))
    raise ValueError('Unsupported guild failure kind')
