"""Pet automatic consumable admission driven by the pinned native effect vector.

Native 0x8A1 type 2 registers the two automatic slots as ``{0: binding,
1: binding}``; 0x65E asks the server to consume one already registered
consumable. The upstream handler admitted only a hand-written template
allowlist, so every ordinary recovery potion the player actually owns was
rejected with ``0x8A2 result=-1`` and the slot stayed empty. The MP slot check
also accepted effect kind 2 only, which locked out proportional MP recovery
(kind 19), i.e. every "N% MP" potion.

This module keeps the native framing and replaces only the admission test:

* a bag-group-6 consumable qualifies when *all* of its pinned effects are plain
  recovery (1 flat HP, 2 flat MP, 13 proportional HP, 19 proportional MP);
* the HP slot needs {1,13}, the MP slot needs {2,19}, so a full HP+MP potion
  fits either slot;
* buffs, apples, elixirs, infinite rows and the previously denied templates
  keep their existing manual-only decisions.

Every 0x8A2 echoes the persisted map, so a rejection never blanks the client.

A *wait* is not a rejection. 0x65E arrives again as soon as the client decides
the slot is due, so a potion that is still cooling down (or a pet interval that
has not elapsed) was answered with ``result=-1``; the client retried at once
(fifty-six requests inside three seconds in the 2026-11-05 capture) and drew one
empty confirm box, because -1 is outside the client's 0..0xC4D error table and
resolves to an empty string (see ``social_messages.chat_ack``). A wait is now
answered with ``result=0``, the real remaining seconds on the native cooldown
field, and one throttled system line in the chat window instead.

Player-facing refusals (no pet, empty slot, nothing eligible in the bag, level)
take the same route through ``REFUSAL_TEXT``: acknowledged with ``result=0`` and
explained in chat. Only protocol and authority faults keep ``-1``.
"""
import hashlib
import json
import math
import sqlite3
import struct
import time
from contextlib import closing
from pathlib import Path

LOG = Path(__file__).resolve().parents[2] / 'state/pet-auto.log'

RECOVERY = frozenset((1, 2, 13, 19))
HP_KINDS = frozenset((1, 13))
MP_KINDS = frozenset((2, 19))
DENIED = frozenset((710022, 710313, 710314, 710315, 77110, 79065, 130467, 710193, 723674))
BIND_PHASES = frozenset(('town_ready', 'field_active', 'dungeon_active'))
USE_PHASES = frozenset(('town_ready', 'field_active', 'dungeon_active'))


def _log(entry):
    entry['time'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open('a', encoding='utf8') as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + '\n')
    except OSError:
        pass


class Waiting(ValueError):
    """A normal reuse wait, never surfaced as -1.

    Every other admission failure keeps its -1 rejection. These two are the
    "not yet" states the client walks into by itself, so they are answered with
    a success acknowledgement carrying the remaining seconds plus one chat line.
    """

    def __init__(self, reason, seconds, template=None):
        super().__init__(reason)
        self.reason = reason
        self.seconds = max(0.0, float(seconds))
        self.template = template


# One chat line per slot/reason window; the client re-asks immediately and a
# retry storm must not scroll the chat window away.
NOTICE_SECONDS = 4.0


def _item_name(template):
    if type(template) is not int:
        return '道具'
    try:
        from els_server.game_data import client_data
        return client_data().item(template)['name'] or '道具'
    except (ValueError, KeyError, sqlite3.Error):
        return '道具'


def _notice_text(waiting):
    seconds = max(1, int(math.ceil(waiting.seconds)))
    if waiting.reason == 'pet-interval':
        return '[系统] 宠物自动使用间隔尚未结束，请稍后再试。（剩余 %d 秒）' % seconds
    return '[系统] 「%s」的冷却时间尚未结束，无法使用。（剩余 %d 秒）' % (_item_name(waiting.template), seconds)


def _throttled(session, key):
    now = time.time()
    seen = session.__dict__.setdefault('pet_auto_notices', {})
    last = seen.get(key)
    if last is not None and now - last < NOTICE_SECONDS:
        return True
    if len(seen) > 16:
        seen.clear()
    seen[key] = now
    return False


# Player-facing refusals stay in the chat window; -1 would only draw an empty
# box. Anything not listed here is a protocol/authority fault the player cannot
# act on, so its -1 rejection stays visible and diagnosable.
REFUSAL_TEXT = {
    'Active pet and automatic entitlement required': '[系统] 没有正在使用的宠物，无法自动使用道具。',
    'Empty automatic slot': '[系统] 尚未设置自动使用的道具，请先在宠物界面中设置。',
    'No eligible owned consumable': '[系统] 背包中没有可自动使用的恢复道具。',
    'Consumable level requirement': '[系统] 角色等级不足，无法自动使用该道具。',
    'Consumable character level': '[系统] 角色等级不足，无法自动使用该道具。',
    'Consumable is excluded from automatic use': '[系统] 该道具无法自动使用。',
    'Infinite consumable is not consumed automatically': '[系统] 该道具无法自动使用。',
    'Consumable outside the pinned catalog': '[系统] 该道具无法自动使用。',
    'Consumable effect is not plain HP/MP recovery': '[系统] 该道具无法自动使用。',
    'Consumable carries a native special-use flag': '[系统] 该道具无法自动使用。',
}


def _notice(session, text):
    from els_server.protocol import social_messages as wire
    from els_server.protocol.protocol_codec import encode_event
    identity = getattr(session, 'identity', None)
    account_id = identity['id'] if isinstance(identity, dict) and 'id' in identity else session.account.account_id
    notice = wire.chat_notice(session.account.character(), account_id, text, 0)
    encode_event(notice)
    return notice


def _waiting_reply(session, slot, waiting):
    from els_server.protocol.consumable_messages import acknowledgement
    _log(dict(event='use-waiting', owner=session.account.uid, slot=slot, reason=waiting.reason,
              template=waiting.template, seconds=round(waiting.seconds, 3)))
    # Success framing keeps the client out of its empty error dialog; the
    # native cooldown field is what the slot icon counts down from.
    reply = [acknowledgement(result=0, cooldown=waiting.seconds, automatic=True, slot=slot)]
    if not _throttled(session, (slot, waiting.reason)):
        reply.append(_notice(session, _notice_text(waiting)))
    return reply


def _refusal_reply(session, slot, reason):
    from els_server.protocol.consumable_messages import acknowledgement
    text = REFUSAL_TEXT[reason]
    _log(dict(event='use-refused', owner=session.account.uid, slot=slot, reason=reason, notice=text))
    reply = [acknowledgement(result=0, automatic=True, slot=slot)]
    if not _throttled(session, (slot, 'refuse:' + reason)):
        reply.append(_notice(session, text))
    return reply


def metadata(template, level):
    """Return (catalog row, effect kinds) when a template may be auto-consumed."""
    from els_server.domain.consumable_extensions import infinite
    from els_server.domain.consumables import catalog
    if template in DENIED:
        raise ValueError('Consumable is excluded from automatic use')
    if infinite(template):
        raise ValueError('Infinite consumable is not consumed automatically')
    row = catalog().get(template)
    if row is None:
        raise ValueError('Consumable outside the pinned catalog')
    raw = bytes.fromhex(row['record_hex'])
    kinds = tuple(struct.unpack_from('<I', bytes.fromhex(h))[0] for h in row['effects'])
    if not kinds or not set(kinds) <= RECOVERY:
        raise ValueError('Consumable effect is not plain HP/MP recovery')
    if struct.unpack_from('<I', raw, 0xa8)[0]:
        raise ValueError('Consumable carries a native special-use flag')
    if type(level) is not int or not 1 <= level <= 99:
        raise ValueError('Consumable character level')
    if level < raw[0xd1]:
        raise ValueError('Consumable level requirement')
    return row, kinds


def bindings_ack(state=None, result=0):
    from els_server.protocol.companion_messages import event
    from els_server.storage.pet_support import DEFAULT
    state = dict(DEFAULT if state is None else state)
    return event(0x8a2, struct.pack('>ii', result, 2)
                 + struct.pack('>Iiiii', 2, 0, state['hp_binding'], 1, state['mp_binding']))


def _decode(payload):
    if not isinstance(payload, bytes) or len(payload) != 24:
        raise ValueError('Automatic binding map length')
    kind, count = struct.unpack_from('>iI', payload)
    if kind != 2 or count != 2:
        raise ValueError('Automatic binding map type/count')
    entries = dict(struct.unpack_from('>ii', payload, 8 + 8 * n) for n in range(2))
    if set(entries) != {0, 1} or any(value < 0 for value in entries.values()):
        raise ValueError('Automatic binding keys')
    return entries


def _candidates(db, owner, level):
    from els_server.domain.quick_bindings import item_binding
    from els_server.storage.inventory_state import load_items
    found = {}
    for item in load_items(db, owner):
        if item['group'] != 6:
            continue
        try:
            _, kinds = metadata(item['template'], level)
        except ValueError:
            continue
        found[item_binding(item['template'])] = kinds
    return found


def _bind(session, payload):
    from els_server.storage.pet_support import automatic, ensure, save_automatic
    path = session.account.store.path
    owner = session.account.uid
    if session.role != 'game' or session.phase not in BIND_PHASES:
        _log(dict(event='bind-rejected', owner=owner, reason='phase %s' % (session.phase,)))
        return [bindings_ack(result=-1)]
    try:
        entries = _decode(payload)
    except ValueError as error:
        _log(dict(event='bind-rejected', owner=owner, raw=payload.hex(), reason=str(error)))
        return [bindings_ack(result=-1)]
    state = None
    try:
        with closing(sqlite3.connect(path, timeout=10)) as db:
            try:
                db.execute('BEGIN IMMEDIATE')
                ensure(db)
                state = automatic(db, owner)
                if not state['automatic']:
                    raise ValueError('Pet automatic slot is locked')
                level = db.execute('SELECT level FROM characters WHERE uid=?', (owner,)).fetchone()
                if level is None:
                    raise ValueError('Unknown automatic consumable owner')
                candidates = _candidates(db, owner, level[0])
                for slot, key in ((0, 'hp_binding'), (1, 'mp_binding')):
                    binding = entries[slot]
                    if binding:
                        if binding not in candidates:
                            if binding != state[key]:
                                raise ValueError('Unowned or unsupported automatic consumable %d' % binding)
                        elif not set(candidates[binding]) & (HP_KINDS if slot == 0 else MP_KINDS):
                            raise ValueError('Automatic consumable does not restore the selected resource')
                    state[key] = binding
                state.pop('automatic_expires_at', None)
                save_automatic(db, owner, state)
                db.commit()
            except BaseException:
                db.rollback()
                raise
        _log(dict(event='bind', owner=owner, requested=entries,
                  candidates={str(k): list(v) for k, v in candidates.items()}, result='ok'))
        with closing(sqlite3.connect(path)) as mirror:
            saved = automatic(mirror, owner)
        return [bindings_ack(saved, result=0)]
    except ValueError as error:
        _log(dict(event='bind-rejected', owner=owner, raw=payload.hex(), requested=entries, reason=str(error)))
        return [bindings_ack(state, result=-1)]


def _use(session, payload, sequence):
    from els_server.domain.equipment_chip_flow import current_lease
    from els_server.protocol.consumable_messages import acknowledgement, effect, request as parse
    if session.role != 'game' or session.phase not in USE_PHASES or not current_lease(session):
        return [acknowledgement(result=-1, automatic=True)]
    try:
        slot = parse(payload, automatic=True)
    except ValueError:
        _log(dict(event='use-rejected', owner=session.account.uid, reason='request shape'))
        return [acknowledgement(result=-1, automatic=True)]
    operation = session.shop_session_id + ':auto:' + str(sequence)
    try:
        answer = _consume(session.account.store.path, session.account.uid, slot, operation,
                          account_id=session.account.account_id)
    except Waiting as waiting:
        return _waiting_reply(session, slot, waiting)
    except ValueError as error:
        _log(dict(event='use-rejected', owner=session.account.uid, slot=slot, reason=str(error)))
        if str(error) in REFUSAL_TEXT:
            return _refusal_reply(session, slot, str(error))
        return [acknowledgement(result=-1, automatic=True)]
    return answer


def _consume(path, owner, slot, operation, *, now=None, account_id=None):
    from els_server.domain.item_expiration import expired
    from els_server.domain.quick_bindings import item_binding
    from els_server.storage.inventory_state import load_items
    from els_server.storage.pet_support import active_effects, automatic, ensure, owned_pet
    from els_server.protocol.consumable_messages import acknowledgement, effect
    from els_server.domain.consumables import recovery_cooldown_seconds
    if not isinstance(operation, str) or not 1 <= len(operation) <= 160:
        raise ValueError('Automatic consumable operation identity')
    digest = hashlib.sha256(str(owner).encode() + b':auto:' + bytes([slot])).hexdigest()
    with closing(sqlite3.connect(path, timeout=10)) as db:
        try:
            db.execute('BEGIN IMMEDIATE')
            now = time.time() if now is None else now
            ensure(db)
            character = db.execute('SELECT level FROM characters WHERE uid=?', (owner,)).fetchone()
            if character is None:
                raise ValueError('Unknown consumable owner')
            if account_id is not None:
                from els_server.storage.profession_state import require_owner
                require_owner(db, owner, account_id)
            from els_server.storage.character_lifecycle import exists as lifecycle_exists
            if lifecycle_exists(db):
                lifecycle = db.execute('SELECT requested_at,finalized_at FROM character_lifecycle WHERE uid=?',
                                       (owner,)).fetchone()
                if lifecycle and any(lifecycle):
                    raise ValueError('Unavailable consumable character')
            pending = None
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='consumable_uses'").fetchone():
                pending = db.execute('SELECT request_hash FROM consumable_uses WHERE operation_id=?',
                                     (operation,)).fetchone()
            if pending:
                if pending[0] != digest:
                    raise ValueError('Conflicting consumable retry')
                return [acknowledgement(automatic=True, slot=slot)]
            state = automatic(db, owner, now=int(now))
            row = (db.execute('SELECT pet FROM companion_active WHERE owner=?', (owner,)).fetchone()
                   if db.execute("SELECT 1 FROM sqlite_master WHERE name='companion_active'").fetchone() else None)
            if not state['automatic'] or not row or not row[0] or (state['upgrade'] and not state['enabled']):
                raise ValueError('Active pet and automatic entitlement required')
            owned_pet(db, owner, row[0])
            binding = state['hp_binding' if slot == 0 else 'mp_binding']
            interval = state['hp_seconds' if slot == 0 else 'mp_seconds'] if state['upgrade'] else 0
            db.execute('CREATE TABLE IF NOT EXISTS pet_auto_cooldowns (owner INTEGER NOT NULL, '
                       'slot INTEGER NOT NULL, ready_at REAL NOT NULL, PRIMARY KEY(owner,slot))')
            last = db.execute('SELECT ready_at FROM pet_auto_cooldowns WHERE owner=? AND slot=?',
                              (owner, slot)).fetchone()
            if last and now < last[0]:
                raise Waiting('pet-interval', last[0] - now)
            if not binding:
                raise ValueError('Empty automatic slot')
            eligible = []
            for item in load_items(db, owner):
                if item['group'] != 6 or expired(item, now=int(now)):
                    continue
                if item_binding(item['template']) != binding:
                    continue
                try:
                    meta, _ = metadata(item['template'], character[0])
                except ValueError:
                    continue
                eligible.append((item, meta))
            if not eligible:
                raise ValueError('No eligible owned consumable')
            item, meta = min(eligible, key=lambda pair: ('expires_at' not in pair[0],
                                                         pair[0].get('expires_at', 0),
                                                         pair[0]['slot'], pair[0]['uid']))
            db.execute('CREATE TABLE IF NOT EXISTS consumable_cooldowns (owner INTEGER NOT NULL, '
                       'cooldown_group INTEGER NOT NULL, ready_at REAL NOT NULL, PRIMARY KEY(owner,cooldown_group))')
            prior = db.execute('SELECT ready_at FROM consumable_cooldowns WHERE owner=? AND cooldown_group=?',
                               (owner, meta['cooldown_group'])).fetchone()
            if prior and now < prior[0]:
                raise Waiting('item-cooldown', prior[0] - now, item['template'])
            remaining = dict(item, count=item['count'] - 1) if item['count'] > 1 else None
            answer = [acknowledgement(remaining, (item['group'], item['slot']), item['template'],
                                      automatic=True, slot=slot),
                      effect(owner, item['template'])]
            from els_server.protocol.protocol_codec import encode_event
            for event in answer:
                encode_event(event)
            if remaining:
                db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?', (item['uid'], owner))
            else:
                from els_server.storage.item_instances import remove
                remove(db, owner, item)
            reduction = max(0, min(.9, active_effects(db, owner).get('m_fReduceRecoveryItemCooltime', 0)))
            db.execute('INSERT INTO consumable_cooldowns VALUES (?,?,?) ON CONFLICT(owner,cooldown_group) '
                       'DO UPDATE SET ready_at=excluded.ready_at',
                       (owner, meta['cooldown_group'],
                        now + recovery_cooldown_seconds(meta['cooldown_seconds'], reduction)))
            db.execute('INSERT INTO pet_auto_cooldowns VALUES (?,?,?) ON CONFLICT(owner,slot) '
                       'DO UPDATE SET ready_at=excluded.ready_at', (owner, slot, now + interval))
            db.execute('CREATE TABLE IF NOT EXISTS consumable_uses (operation_id TEXT PRIMARY KEY, '
                       'request_hash TEXT NOT NULL, owner INTEGER NOT NULL, item_uid INTEGER NOT NULL, '
                       'template INTEGER NOT NULL, used_at REAL NOT NULL)')
            db.execute('INSERT INTO consumable_uses VALUES (?,?,?,?,?,?)',
                       (operation, digest, owner, item['uid'], item['template'], now))
            db.commit()
            _log(dict(event='use', owner=owner, slot=slot, template=item['template'],
                      remaining=None if remaining is None else remaining['count']))
            return answer
        except BaseException:
            db.rollback()
            raise


def handle(session, event, sequence):
    if event.event_id != 0x202 or event.kind not in (0x8a1, 0x65e):
        return None
    if (getattr(session, 'client_build', None) != 'dx11_260923'
            or not getattr(session, 'item_test', False)
            or getattr(session, 'account', None) is None
            or getattr(session.account, 'store', None) is None):
        return None
    if event.kind == 0x8a1:
        if len(event.payload) < 4 or event.payload[:4] != b'\0\0\0\2':
            return None
        return _bind(session, event.payload)
    return _use(session, event.payload, sequence)


_log(dict(event='loaded'))
