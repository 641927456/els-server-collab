"""Read-only finite search qualification from the existing consumable consumer.

This checks foreign offer contents; it never grants ownership, fills shortcuts,
unseals, sends 113/115, or calls the transactional consumer. The caller binds the
real role/SQL/read-snapshot clock and obtains app_gate from the actual session.
No HP/MP saturation rule is added: the current server consumer has no such gate.
"""
from dataclasses import dataclass
import math

RECOVERY = frozenset((77000,77010,77170,77180,77190,77270,77420,77430,
                     78902,78930,78985,78986,710000,710022,79063,79064,79065,77110))
APPLES = frozenset((710313,710314,710315))
SUPPORTED = RECOVERY | APPLES
STAGE_AND_LOCK = APPLES | frozenset((77110,))


@dataclass(frozen=True)
class AutomaticContext:
    automatic: bool | None
    active_owned_pet: bool | None
    upgrade: bool | None
    enabled: bool | None
    configured_binding: int | None
    slot_ready_at: float | None


@dataclass(frozen=True)
class ConsumableContext:
    app_gate: bool | None
    level: int | None
    character_available: bool | None
    cooldowns: dict | None
    native_stage_ready: bool | None = None
    automatic: AutomaticContext | None = None


def canonical_app_gate(session, current_lease):
    """Mirror local_session dispatch and consumable_flow admission, read-only.

current_lease must be the real existing lease predicate supplied by the caller.
Tests may provide fixtures, but those do not qualify a live session or lease.
"""
    try:
        if (session.item_test is not True or session.client_build != 'dx11_260923'
                or session.role != 'game' or session.phase != 'dungeon_active'
                or session.account.store is None
                or session.account.store.uid != session.account.uid):
            return False
    except AttributeError:
        return None
    if not callable(current_lease):
        return None
    value = current_lease(session)
    if type(value) is not bool:
        raise ValueError('Canonical lease predicate must return bool')
    return value


def canonical_rules():
    from els_server.domain.consumables import require_usable
    from els_server.domain.item_expiration import expired
    from els_server.domain.item_locks import locked
    from els_server.domain.quick_bindings import item_binding
    return require_usable, expired, locked, item_binding


def _known_bool(value, label):
    if value is not None and type(value) is not bool:
        raise ValueError(label)
    return value


def _clock(value, label):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(label)
    return value


def eligible(item, context, *, now, automatic=False, automatic_slot=0, rules=None):
    """Return True/False for this finite consumer, None for missing required facts.

The full native item record must already be validated by the actual offer
snapshot provider. Sealed acquisition policy belongs to the caller; an item
still explicitly sealed is unknown here and is never rewritten. UID, owner,
bag/slot and shortcut inventory selection are deliberately not fabricated.
Automatic checks include the actual configured binding, entitlement and timer.
"""
    if not isinstance(item, dict) or type(item.get('template')) is not int:
        raise ValueError('Validated foreign offer item required')
    if item['template'] not in SUPPORTED:
        return None
    if not isinstance(context, ConsumableContext) or type(automatic) is not bool:
        raise ValueError('Consumable query context')
    now = _clock(now, 'Snapshot clock')
    gate = _known_bool(context.app_gate, 'App gate')
    if gate is False:
        return False
    if gate is None:
        return None
    available = _known_bool(context.character_available, 'Character availability')
    if available is False:
        return False
    if available is None or context.level is None:
        return None
    if type(context.level) is not int or not 1 <= context.level <= 99:
        raise ValueError('Current role level')
    if type(item.get('count')) is not int or item['count'] <= 0 or item.get('metadata') != 2:
        raise ValueError('Finite ordinary consumable contents')
    sealed = item.get('sealed', False)
    if type(sealed) is not bool:
        raise ValueError('Native sealing state')
    if sealed:
        return None
    require_usable, expired, locked, item_binding = canonical_rules() if rules is None else rules
    try:
        meta = require_usable(item['template'], context.level, automatic=automatic)
    except ValueError as error:
        if str(error) in ('Consumable level requirement', 'Apple pet automation is not admitted',
                          'Extended consumables require manual use'):
            return False
        raise
    if expired(item, now=int(now)):
        return False
    if item['template'] in STAGE_AND_LOCK:
        if locked(item, now=int(now)):
            return False
        stage = _known_bool(context.native_stage_ready, 'Native actor stage readiness')
        if stage is not True:
            return stage
    if context.cooldowns is None:
        return None
    if not isinstance(context.cooldowns, dict):
        raise ValueError('Actual same-group cooldown snapshot')
    prior = context.cooldowns.get(meta['cooldown_group'])
    if prior is not None and now < _clock(prior, 'Canonical cooldown ready_at'):
        return False
    if automatic:
        if type(automatic_slot) is not int or automatic_slot not in (0, 1):
            raise ValueError('Automatic slot')
        state = context.automatic
        if state is None:
            return None
        if not isinstance(state, AutomaticContext):
            raise ValueError('Automatic canonical context')
        auto = _known_bool(state.automatic, 'Pet automatic entitlement')
        pet = _known_bool(state.active_owned_pet, 'Actual active owned pet')
        upgrade = _known_bool(state.upgrade, 'Pet automatic upgrade')
        enabled = _known_bool(state.enabled, 'Pet automatic enabled')
        if auto is False or pet is False or (upgrade is True and enabled is False):
            return False
        if auto is None or pet is None or upgrade is None or (upgrade and enabled is None):
            return None
        if state.configured_binding is None or state.slot_ready_at is None:
            return None
        if type(state.configured_binding) is not int or state.configured_binding < 0:
            raise ValueError('Actual automatic slot binding')
        if not state.configured_binding or state.configured_binding != item_binding(item['template']):
            return False
        if now < _clock(state.slot_ready_at, 'Pet slot timer ready_at'):
            return False
    return True
