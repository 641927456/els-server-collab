"""The current pet-information UI's original nutrient and digestive requests.

Upstream admitted these three requests only while the session stood in a stable
native town (it reused the housing actor capture). The pet-information window is
also opened in the field and inside a dungeon, so every drag made there was
answered with ``result=-1`` and the panels stayed at zero. The guard below keeps
the same identity and session checks but accepts the three ordinary play phases,
matching the automatic-consumable admission already in use.
"""
import json
import sqlite3
import time
from pathlib import Path
from els_server.protocol import pet_progression_messages as wire

LOG = Path(__file__).resolve().parents[2] / 'state/pet-nutrition.log'
PHASES = frozenset(('town_ready', 'field_active', 'dungeon_active'))

# The pet record itself carries the digested HH:MM:SS, so the protocol module
# that owns it has to be current before this handler answers.
_DEPS = ('els_server.protocol.companion_messages',
         'els_server.protocol.pet_progression_messages',
         'els_server.storage.pet_progression',
         'els_server.domain.pet_digestion',
         'els_server.storage.pet_nutrition')
_STAMP = {}


def _refresh_deps():
    import importlib
    import os
    import sys
    for name in _DEPS:
        try:
            module = sys.modules.get(name) or importlib.import_module(name)
            path = getattr(module, '__file__', None)
            stamp = (os.path.getmtime(path), os.path.getsize(path))
            if _STAMP.get(name) != stamp:
                _STAMP[name] = stamp
                importlib.reload(module)
        except Exception:
            pass


def _log(entry):
    entry['time'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open('a', encoding='utf8') as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + '\n')
    except OSError:
        pass


def _guard(s):
    """Identity/session guard without the town-only restriction."""
    from els_server.domain.town_travel_flow import _ordinary_actor

    def current():
        a = s.account
        if (not _ordinary_actor(s) or a.characters is None or s.role != 'game'
                or s.phase not in PHASES or s.client_build != 'dx11_260923'
                or not s.item_test):
            raise ValueError('Pet nutrient stable actor')
        return (a.uid, a.account_id, s.shop_session_id, s.active_map, s.phase)

    values = current()

    def same():
        try:
            return current() == values
        except (ValueError, AttributeError):
            return False

    def guard(db):
        # The write transaction must still belong to the same actor generation.
        if not same():
            raise ValueError('Pet nutrient actor generation changed')

    return same, guard


def handle(s, event, sequence):
    if event.event_id != 0x202:
        return None
    if event.kind == 0x2ea:
        # The pet list reply carries the shared pet record, so refresh the
        # protocol dependency before the ordinary handler encodes it.
        if s.client_build == 'dx11_260923':
            _refresh_deps()
            # The client keeps the last record it was handed and gates the
            # nutrient window on it, so record exactly when it asks again.
            try:
                from els_server.storage.companion_state import snapshot
                pets = [p for p in snapshot(s.account.store.path, s.account.uid)['companions']
                        if p['kind'] == 'pet']
                stamp = int(time.time())
                _log(dict(event='panel', digest=[p['uid'] for p in pets],
                          until=[p['digest_until'] for p in pets],
                          hours=[round((p['digest_until'] - stamp) / 3600, 1) for p in pets]))
            except Exception:
                pass
        return None
    if event.kind not in (0x8ad, 0x8af, 0x8b9) or s.client_build != 'dx11_260923':
        return None
    failure = {0x8ad: wire.nutrient, 0x8af: wire.investment, 0x8b9: wire.digestion}[event.kind]
    _refresh_deps()
    try:
        same, guard = _guard(s)
        if (event.performers not in ((), (0,)) or event.uid != event.target_uid
                or event.uid != 2 ** 64 - 1 or event.payload_mode != 0
                or type(sequence) is not int or not 1 <= sequence < 2 ** 32):
            raise ValueError('Pet nutrient original envelope')
        from els_server.storage.pet_nutrition import perform
        operation = s.shop_session_id + ':pet-nutrient:' + str(s.account.uid) + ':' + str(sequence)
        answer = perform(s.account.store.path, s.account.uid, s.account.account_id, event.kind, event.payload, operation, guard)
        # The transaction is committed; a failed peer-cache refresh must never
        # turn the already-committed answer into a client-side failure.
        try:
            from els_server.domain.companion_peer_sync import invalidate
            invalidate(s)
        except Exception:
            pass
        _log(dict(event='ok', kind=hex(event.kind), phase=s.phase, sequence=sequence,
                  results=[e.kind for e in answer]))
        return answer
    except (ValueError, sqlite3.Error, OverflowError, AttributeError) as exc:
        _log(dict(event='failed', kind=hex(event.kind), phase=getattr(s, 'phase', None),
                  sequence=sequence, reason=str(exc), payload=event.payload.hex()))
        if 'same' in locals() and not same():
            return []
        return [failure(result=-1)]
