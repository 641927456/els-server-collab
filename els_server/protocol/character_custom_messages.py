"""c881 original 4CB/4CC/4CD, 2A owned map and 18E actor selection wire."""
import os
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.character_custom import canonical,slot_value,selection_type,custom_type,SLOT_TYPES,COUNTS

def _u32(n):return struct.pack('>I',n)
def _text(s):
    raw=s.encode('utf-16le')
    return _u32(len(raw))+raw

# 0x18E is OFF by default. Decompiled 2026-11-08 21:40 (see
# docs/repairs/dungeon-custom-20261108.md 13.8/13.9): the 0x18E reader is
# `FUN_140c4e700` (reached from the dispatcher `0x30C39C0` at `0x30C4154`) and
# it starts with `need(0x1c)` -> read u8 -> read 8 raw bytes -> read a
# `u32`-counted `vector<0x408>` -> two blocks of 7 u32 -> i32 -> owned map ->
# u8 -> a 0x3EC actor block -> ...  Our wire is
# `u64 uid + u32 kind + u32 title + u32 count + {byte family, u32 n, Info*n}`,
# so the client is misaligned from byte 0 and every `read`/`need` after that
# fails.  `FUN_140c4e700` then leaves the stack object at its default value and
# the 0x18E branch immediately hands that object to the target actor's virtual
# at `[vtable+0xC8]` -- i.e. each notice *resets* the actor's customisation to
# the career default.  That is why every one of the five 0x18E shapes measured
# inert (slot-keyed, family-keyed, flattened, before/after the opener, selector
# 1): none of them could ever reach the fields they were tuning.
#
# Suppressing is the safe direction: the frame cannot succeed today, so dropping
# it can only leave the client's own state (2A login tail + the 4CD
# registrations) intact.  Set ELS_ENABLE_18E_NOTICE=1 to put it back on the wire
# for a byte-level comparison against a real server capture.
_ENABLE_18E_NOTICE = os.environ.get('ELS_ENABLE_18E_NOTICE', '0') == '1'

def info(value):
    if value!=canonical(value.get('custom_id')):raise ValueError('Noncanonical permanent custom tuple')
    return struct.pack('>ii',value['custom_id'],value['ability'])+_text(value['date1'])+_text(value['date2'])+struct.pack('>i',value['variant'])

def selection_map(values):
    if not isinstance(values,dict):raise ValueError('Unsupported custom slot')
    return _u32(len(values))+b''.join(bytes([k])+info(slot_value(k,v)) for k,v in sorted(values.items()))

def empty_info():
    """A slot of a family the player has not chosen anything for."""
    return struct.pack('>ii',0,0)+_text('')+_text('')+struct.pack('>i',0)

def family_selection(values):
    """0x18E's own shape: one entry per custom FAMILY, one Info per rank.

    Measured 2026-11-08 16:25. Every measurement up to then had sent the
    selection as one entry per *slot* (keys 3,4,5,6 for the four skill-cut-in
    ranks, 1/10/11/12 for the four wait motions, ...). Under that form the
    window resolved exactly the two single-rank families the user ever saw work
    -- the skill frame (16) and the portrait (19) -- and painted every
    multi-rank tab, cut-ins included, with the career default. A single-rank
    family serialises to the identical bytes under either reading, which is why
    those two kept working while nothing else did.

    So the key is the collapsed family (`selection_type`), and its value is a
    full-length vector in that family's slot order: index 0 is the first rank
    (`CT_SKILL_CUTIN`), index 3 the last (`CT_SKILL_CUTIN_FOURTH`). Ranks the
    player has not chosen carry a zero Info rather than a short vector.
    """
    if not isinstance(values,dict):raise ValueError('Unsupported custom slot')
    groups={}
    for slot,value in values.items():
        groups.setdefault(selection_type(slot),{})[slot]=slot_value(slot,value)
    result=_u32(len(groups))
    for family,rows in sorted(groups.items()):
        slots=sorted(slot for slot,owner in SLOT_TYPES.items() if owner==family)
        if not slots:raise ValueError('Unsupported custom family')
        result+=bytes([family])+_u32(len(slots))
        result+=b''.join(info(rows[slot]) if slot in rows else empty_info() for slot in slots)
    return result

def _key_by_ct():
    """实验开关：+0x6B9 的 key 用 CT（槽号）而不是折叠族。

    依据：客户端 `Enum.tables.json` 的 CUSTOMIZING_TYPE 是 1..28 的连续枚举，
    四个待机动作分别是 CT_WAIT_MOTION=1 / CT_WAIT_MOTION2=10 / CT_WAIT_MOTION3=11 /
    CT_WAIT_MOTION4=12 —— 四个不同的 CT。而 `0x4CD` 的登记记录元素实测步长 0x4C
    (76 字节：custom_id/ability/date1/date2/variant)，**没有 CT 字段**，所以客户端
    无法从登记表里知道「第几档」。CT 作 key 是这个字段唯一还没试过的形态。

    用文件开关而不是环境变量：`dto_tail` 是函数内 import 的，读文件即生效，
    不用重启服务端。删掉文件就回到原行为。

    注意：上一轮把它们混为一谈了 —— §11.7 第 12 条否掉的是「族」作 key 的形态。
    """
    import os
    try:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.exists(os.path.join(root, 'state', 'custom-ids-by-ct.flag'))
    except Exception:
        return False


def selection_ids(values):
    """The login DTO's `+0x6B9`: `map<i32, vector<i32>>`, key -> chosen ids.

    Read out of the retained image rather than guessed: `0xDA3370` (the 2A
    deserializer) reaches `+0x6B9` at `0xDA35AD` through `0xDB6F10`, which does
    `need(0x18)` then hands the cursor to `0xDD7C30`. That one reads a `u32`
    count and then, per entry, an `i32` key (0xDD7CD6) followed by `0xDB1B00`,
    which is `u32` count + that many `i32`. So the wire form is
    `u32 n, {i32 key, u32 m, i32 x m}` and nothing else -- it cannot carry an
    Info tuple, so the ids are the only thing that can be restored here.

    This is the field the window paints its rows from. Every other carrier was
    measured inert against the row labels (0x4CD before/after the opener with
    both row-type bytes, 0x4CC, 0x18E before and after, the 635 which is two
    empty cash-availability vectors and nothing more), and every login until
    now sent this map empty.

    Two key shapes exist. The default (family keys, rank-ordered vector) is what
    every measurement so far used. `state/custom-ids-by-ct.flag` switches to one
    entry per CT with a single id, which is the shape the CUSTOMIZING_TYPE enum
    (1..28, one value per row) actually describes.
    """
    if not isinstance(values,dict):raise ValueError('Unsupported custom slot')
    if _key_by_ct():
        rows={}
        for slot,value in values.items():
            selection_type(slot)
            rows[slot]=slot_value(slot,value)['custom_id']
        result=_u32(len(rows))
        for slot in sorted(rows):
            result+=struct.pack('>i',slot)+_u32(1)+struct.pack('>i',rows[slot])
        return result
    groups={}
    for slot,value in values.items():
        groups.setdefault(selection_type(slot),{})[slot]=slot_value(slot,value)['custom_id']
    result=_u32(len(groups))
    for family,rows in sorted(groups.items()):
        slots=sorted(slot for slot,owner in SLOT_TYPES.items() if owner==family)
        if not slots:raise ValueError('Unsupported custom family')
        result+=struct.pack('>i',family)+_u32(len(slots))
        result+=b''.join(struct.pack('>i',rows.get(slot,0)) for slot in slots)
    return result

def dto_tail(character):
    """The customization block of the 2A login DTO: `+0x6A8`, `+0x6B8`, `+0x6B9`.

    Kept in this module and called through a function-local import from
    `local_messages.player_initialization` so a hot reload of this file changes
    the next login without restarting the server (`local_session` binds
    `player_initialization` at import time and can never be reloaded).
    """
    custom=(character or {}).get('character_custom') or {}
    owned=custom.get('owned') or {};selected=custom.get('selected') or {}
    ids=selection_ids(selected)
    tail=owned_map(owned)+b'\x01'+ids
    if selected and owned:
        # One line per login frame is the only proof this reached the wire: the
        # 2A is not in the traced-kind list, so without it the fix is invisible
        # until someone reads the window and reports what it painted.
        # The `sel=` field is the +0x6B9 block in hex (100 odd bytes, custom ids
        # only - no names, keys or account data). It is the payload the window
        # is supposed to paint its rows from, so capturing it is what makes the
        # next byte-level comparison against the client's 0xDB1B00 reader
        # possible without dumping the whole 2A.
        from els_server.domain.character_custom import _trace
        _trace('dto tail owned=%d slots=%d tail=%d sel=%s'
               %(sum(len(rows) for rows in owned.values()),len(selected),len(tail),ids.hex()))
    return tail

def owned_map(values):
    if not isinstance(values,dict) or set(values)-set(COUNTS) or any(type(k) is not int for k in values):raise ValueError('Unsupported owned custom type')
    result=_u32(len(values))
    for key,rows in sorted(values.items()):
        if (not isinstance(rows,(tuple,list)) or not rows or len(rows)>COUNTS[key] or len({v['custom_id'] for v in rows})!=len(rows)
            or any(v['custom_id']==0 or custom_type(v['custom_id'])!=key for v in rows)):raise ValueError('Owned custom list')
        result+=bytes([key])+_u32(len(rows))+b''.join(info(v) for v in rows)
    return result

def request(payload):
    # Retain the existing value-only helper; storage also needs the selected key.
    return request_slot(payload)[1]

def request_slot(payload):
    # 11D98B0/11F48D0 sends exactly one selected slot per Apply.
    if not isinstance(payload,bytes) or len(payload)>256 or len(payload)<5 or payload[:4]!=b'\x00\x00\x00\x01':
        raise ValueError('Permanent custom Apply shape')
    slot=payload[4];selection_type(slot)
    if len(payload)<13:raise ValueError('Permanent custom Apply tuple')
    custom_id=struct.unpack_from('>i',payload,5)[0]
    value=canonical(custom_id)
    if payload!=selection_map({slot:value}):raise ValueError('Client custom tuple differs from registered canonical value')
    return slot,value

def acknowledgement(values=None,result=0):
    return Event(0x201,kind=0x4cc,payload=struct.pack('>i',result)+selection_map(values or {}))

def registered(value,item=0,family=None):
    base=custom_type(value['custom_id'])
    if base not in COUNTS:raise ValueError('Unsupported custom registration type')
    # The byte the window buckets the row by is that row's own CUSTOMIZING_TYPE,
    # and in this build the CT value equals the slot number: CT_SKILL_CUTIN=3,
    # CT_SKILL_CUTIN_SECOND=4, CT_WAIT_MOTION3=11, CT_EMOTICON4=27, CT_POINT_MARK=28
    # (`resource-scripts/Enum.tables.json`, CUSTOMIZING_TYPE). SLOT_TYPES collapses
    # each of those groups on purpose -- one wait motion is selectable in slots
    # 1/10/11/12 -- so sending the collapsed family filed rows 2..4 of every
    # multi-slot tab under row 1 and the window painted them with the career
    # default. Single-slot tabs (skill frame 16, hyper effect 15, portrait 19,
    # point mark 28, face 2) were unaffected, which is exactly why the frame row
    # resolved while the rest did not. Callers that know the slot pass it.
    if family is None:family=base
    elif type(family) is not int or SLOT_TYPES.get(family)!=base:
        raise ValueError('Custom registration row type')
    # The leading i32 must be ZERO. The client's 0x4CD reader (hit 0xBB7FA8..
    # 0xBB8034 in the retained image) parses `i32, byte, Info`, then does
    # `cmp dword ptr [rsp+0x50], 0 / jne <epilogue>`: a non-zero value jumps
    # straight to the cleanup-and-return path, so the handler reports success
    # while calling nothing. Only with zero does it reach
    # `call 0x11F2B10(manager+0xDC8, &info)` at 0xBB80EF, which is what actually
    # files the row. We used to pass the granting book's template id here, so
    # every registration the server ever sent was silently dropped -- which is
    # also why swapping the row-type byte between family and slot changed
    # nothing at all. The byte is only compared against 0x1C (28, CT_POINT_MARK)
    # for an extra branch; it never selects the row.
    if type(item) is not int or not 0<=item<2**31:raise ValueError('Custom registration item')
    return Event(0x201,kind=0x4cd,payload=struct.pack('>i',item)+bytes([family])+info(value))

def selected_notice(uid,title,values,kind=0):
    if type(uid) is not int or not 1001<=uid<2**63 or type(title) is not int or not 0<=title<2**31:
        raise ValueError('Custom actor identity/title')
    # `kind` is the otherwise-unexplained u32 that sits between the actor uid
    # and the title. Every caller has always written 0 and the town unit reacts,
    # so 0 is the town/default selector; a dungeon actor is a different object
    # built from the member DTO and may need a non-zero selector to be found.
    # Passing 0 keeps the byte layout identical to the historical wire.
    if type(kind) is not int or not 0<=kind<2**31:
        raise ValueError('Custom actor selector')
    # 30D5C50 ->214E6C0: this i32 is the equipped title. Reuse the current
    # authoritative snapshot; zero is valid only when no eligible title exists.
    # 18E keys selected customs by FAMILY, and each value is one Info per rank
    # of that family. Measured 2026-11-08 16:25: while this frame wrapped every
    # slot on its own, the window resolved exactly the two single-rank families
    # the user ever saw work -- skill frame (16) and portrait (19) -- and painted
    # every multi-rank tab, cut-ins included, with the career default. A
    # single-rank family serialises to the same bytes under either reading,
    # which is why those two were unaffected. See family_selection.
    lists=family_selection(values)
    if not _ENABLE_18E_NOTICE:
        return None
    return Event(0x201,kind=0x18e,payload=struct.pack('>QII',uid,kind,title)+lists)

def opening_information(cash_catalog):
    """23AD020: two cash-sale ID vectors, no result/status prefix.

    The existing D79 authority currently publishes no normal cash products.
    Fail closed if that authority changes: never publish stale hardcoded
    availability or substitute the independent ED catalog/owned SQL state.
    """
    if (not isinstance(cash_catalog,Event)or cash_catalog.event_id!=0x201
        or cash_catalog.kind!=0xd79 or cash_catalog.payload!=b'\x01'+bytes(36)):
        raise ValueError('Custom opener cash catalog contract changed')
    return Event(0x201,kind=0x635,payload=bytes(8))
