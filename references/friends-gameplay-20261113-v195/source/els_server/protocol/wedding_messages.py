"""Current original wedding request serializers and inventory acknowledgements."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.social_messages import Reader


def _bool(reader):
    value = reader.scalar('B')
    if value not in (0, 1):
        raise ValueError('Wedding boolean')
    return bool(value)


def _guests(reader):
    count = reader.scalar('I')
    if count > 100:
        raise ValueError('Wedding invitation capacity')
    values = tuple(reader.scalar('Q') for _ in range(count))
    if values != tuple(sorted(set(values))) or any(not 0 < v < 2**63 for v in values):
        raise ValueError('Original wedding guest UID set')
    return values


def request(kind, payload):
    reader = Reader(payload)
    if kind == 0x887:
        # Original DBF300, packed DTO30C0A70, UI58045 in3081AC0.
        # The UI adds23h59m to the selected date/hour. 308E470 subtracts
        # exactly86340 when displaying it; this scalar is the closing time.
        result = dict(hall=reader.scalar('b'), officiant=reader.scalar('b'),
                      ends_at=reader.scalar('Q'), partner=reader.scalar('Q'),
                      ring=reader.scalar('Q'), public=_bool(reader),
                      message=reader.text(), password=reader.text(),
                      reserved_seats=reader.scalar('b'), guests=_guests(reader))
        if result['hall'] not in (2, 3, 4, 5, 6) or not 0 <= result['officiant'] <= 4:
            raise ValueError('Current native wedding hall/officiant')
        if not 0 <= result['reserved_seats'] <= 30:
            raise ValueError('Wedding reserved guest seats')
        if result['public'] and result['password']:
            raise ValueError('Public wedding password')
    elif kind == 0x889:
        # Original3334180;32B2680 supplies nonnegative page and zero cursor.
        result = dict(page=reader.scalar('i'), cursor=reader.scalar('Q'))
        if result['page'] < 0 or result['cursor'] != 0:
            raise ValueError('Original wedding list page/cursor')
    elif kind == 0x88c:
        # Original DBF710. D33C90 selects a reservation from owned tickets.
        result = dict(reservation=reader.scalar('i'), option=_bool(reader))
    elif kind == 0x88e:
        # Original DBFA90; UI58049 calls D34390.
        result = dict(reservation=reader.scalar('i'), guests=_guests(reader))
    elif kind == 0x88b:
        # Original DBFE10;32B2D30 distinguishes own couple, invited, public.
        result = dict(role=reader.scalar('b'), ticket=reader.scalar('Q'),
                      reservation=reader.scalar('i'), option=_bool(reader),
                      password=reader.text())
        if result['role'] not in (1, 2, 3):
            raise ValueError('Original wedding entry role')
    elif kind == 0x417:
        result = dict(reason=reader.scalar('i'))
        if result['reason'] != 0:
            raise ValueError('Original voluntary wedding exit')
    elif kind == 0x41f:
        result = {}
    elif kind == 0x422:
        # Original2128470 ->21B8410: agree, then false for ordinary marriage.
        result = dict(accepted=_bool(reader), soulmate=_bool(reader))
    elif kind == 0x408:
        count = reader.scalar('I')
        if count > (len(payload)-4)//8:
            raise ValueError('Wedding ticket vector bounds')
        values = tuple(reader.scalar('Q') for _ in range(count))
        if len(set(values)) != len(values) or any(not 0 < v < 2**63 for v in values):
            raise ValueError('Wedding ticket UID vector')
        result = dict(tickets=values)
    else:
        raise ValueError('Unsupported wedding request')
    reader.end()
    return result


def inventory_ack(kind, changes=(), *, result=0):
    # D33590/888 and D344E0/88F both consume result then DD46E0 changes.
    if kind not in (0x888, 0x88f):
        raise ValueError('Wedding inventory acknowledgement kind')
    from els_server.domain.fashion_state import record, empty_record
    changes = tuple(changes)
    body = struct.pack('>iI', (21) if result == -1 else result, len(changes)) + b''.join(
        empty_record(*position) if item is None else record(item)
        for position, item in changes)
    return Event(0x201, kind=kind, payload=body)


def hall_record(row):
    """Original D99F40,207-byte DTO, including current public/private tail."""
    from els_server.domain.item_expiration import date_string
    from els_server.protocol.social_messages import wstring
    if row is None:
        # A failed88D still parses the complete DTO before checking result.
        return (struct.pack('>ibbQQ',0,0,0,0,0)+wstring('')+bytes(8)+wstring('')
                +bytes(10)+wstring('')*3+bytes(7))
    return (struct.pack('>ibbQQ', row['id'], row['hall'], row['officiant'],
                        row['groom'], row['bride'])
            + wstring(date_string(row['ends_at'])) + struct.pack('>Q', row['ends_at'])
            + wstring(row['message']) + struct.pack('>QBB', row['room'], row['success'], row['deleted'])
            + wstring(row['groom_name']) + wstring(row['bride_name']) + wstring(row['password'])
            + struct.pack('>Bbbb', row['public'], row['invited'], row['reserved_seats'], row['guests'])
            + bytes(3))  # Last three native constructor-zero extension fields.


def lobby(rows, pages, *, result=0):
    rows = tuple(rows)
    #32B1930 uses pages at+668; its other scalar and final Q are unread.
    # Preserve their original constructor-zero values without inventing clocks.
    return Event(0x201, kind=0x88a, payload=struct.pack('>iIII', (21) if result == -1 else result, pages, 0, len(rows))
                 + b''.join(hall_record(r) for r in rows) + bytes(8))


def detail(row=None, invited=(), *, result=0):
    if row is None and result==0:raise ValueError('Successful wedding detail needs a saved row')
    invited = tuple(sorted(invited))
    return Event(0x201, kind=0x88d, payload=struct.pack('>i', (21) if result == -1 else result) + hall_record(row)
                 + struct.pack('>I', len(invited)) + b''.join(struct.pack('>Q', u) for u in invited))


def ticket_information(entries, changes=(), *, unsolicited=False, result=0):
    # Original2C20F10: map<UID, current extended KWeddingItemInfo>.
    from els_server.domain.fashion_state import record, empty_record
    from els_server.domain.item_expiration import date_string
    from els_server.protocol.social_messages import wstring
    entries = tuple(sorted(entries, key=lambda entry: entry[0]))
    body = struct.pack('>iI', (21) if result == -1 else result, len(entries))
    for uid, row in entries:
        body += (struct.pack('>QQibbQQ', uid, uid, row['id'], row['hall'], row['officiant'],
                             row['groom'], row['bride'])
                 + wstring(row['groom_name']) + wstring(row['bride_name'])
                 + wstring(date_string(row['ends_at'])) + wstring(row['message'])
                 + wstring(row['password']))
    changes = tuple(changes)
    body += struct.pack('>I', len(changes)) + b''.join(
        empty_record(*position) if item is None else record(item)
        for position, item in changes)
    return Event(0x201, kind=0x409, payload=body+bytes((unsolicited,)))


def acknowledged(kind, *, result=0):
    if kind not in (0x418, 0x420):
        raise ValueError('Wedding acknowledgement kind')
    return Event(0x201, kind=kind, payload=struct.pack('>i', (21) if result == -1 else result))


def consent_requested():
    # Original2127ED0/421 does not read a payload.
    return Event(0x201, kind=0x421, payload=b'')


def consent_notice(accepted):
    # Original2128620/423 reads agree and soulmate flags.
    return Event(0x201, kind=0x423, payload=bytes((accepted, False)))


def ceremony_started(changes=(), *, refresh=False, reminder=False, result=0):
    #424 is START_WEDDING_NOT: marriage state changes and the original
    # direction/cutscene starts here; it is not an animation-finished report.
    from els_server.domain.fashion_state import record, empty_record
    changes = tuple(changes)
    return Event(0x201, kind=0x424,
                 payload=struct.pack('>iBBI', (21) if result == -1 else result, reminder, refresh, len(changes))
                 + b''.join(empty_record(*position) if item is None else record(item)
                            for position, item in changes))


def joined(row, room_body, slots, *, cn_ip='', relay_ip='', relay_port=0, auxiliary='', result=0):
    """Original415: current hall, shared D9BCC0 and ordinary D9DDB0 slots."""
    from els_server.protocol.social_messages import wstring
    slots = tuple(slots)
    return Event(0x201, kind=0x415, payload=struct.pack('>i', (21) if result == -1 else result) + hall_record(row)
                 + room_body + struct.pack('>I', len(slots)) + b''.join(slots)
                 + wstring(cn_ip) + wstring(relay_ip) + struct.pack('>H', relay_port)
                 + wstring(auxiliary))


def arrived(slot):
    # BB64B0 -> C4E570 reads D9DDB0 slot, i32 start index and an extra Q.
    # That consumer derives the wedding position from FullUser+48C; the
    # extra two constructor-zero fields are not used by its wedding path.
    return Event(0x201,kind=0x416,payload=slot+bytes(12))


def left(uid, slots, *, reason=0, state=0, auxiliary=0):
    # Original2127740/419: reason, state, departing UID, slots, extra Q.
    slots = tuple(slots)
    return Event(0x201, kind=0x419, payload=struct.pack('>ibQI', reason, state, uid, len(slots))
                 + b''.join(slots) + struct.pack('>Q', auxiliary))
