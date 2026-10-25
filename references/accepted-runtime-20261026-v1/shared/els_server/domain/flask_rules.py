"""Flask current fees/gauge/bonus, with explicitly authorized local reward/XP policy.

The random pool, weights, units consumed and XP formula are server-local rules,
not claimed retail probabilities. No old manufacturing outcome is substituted.
"""
import hashlib
import struct
from dataclasses import replace
from els_server.game_data import client_data
from els_server.profession_data import profession_data

POLICY = 'flask-local-policy-20261024-v2'
POOL = (130208, 118205, 118204)
WEIGHTS = ((80, 10, 10), (70, 15, 15), (50, 25, 25), (30, 35, 35), (20, 40, 40))
QUANTITIES = (1, 1, 2, 3, 5)
FEES = (0, 100, 1000, 10000, 20000)
BONUS_IDENTITIES = {
    710159: '9f0fa96e8f4dab79a75d6c933c5526790b1678685574fea3c8164dca6ca0791c',
    710084: 'e41ea950550040e4a476f6ab5e83af2c867bd6a879549e7cad195079bc382c99',
}


def special_inventory_definitions():
    """Two exact current bonus IDs: standard type7, metadata2, bag4, native500."""
    for template, expected in BONUS_IDENTITIES.items():
        row = client_data().item(template)
        raw = row['record']
        if (hashlib.sha256(raw).hexdigest() != expected or row['item_type'] != 7
                or row['metadata'] != 2 or row['flags8'] != 56
                or struct.unpack_from('<I', raw, 0x10)[0] != 500):
            raise ValueError('Flask bonus original item identity')
        yield dict(template=template, metadata=2, group=4, max_stack=500)


def settings():
    source = profession_data()
    maximum, = source.registrations('SetMaxAccumulatedBonusCount')
    if maximum != [7]:
        raise ValueError('Flask weekly maximum resource drift')
    caps = dict(source.registrations('SetMaxAccumulatedEDByLevel'))
    expected_caps = (300000, 600000, 900000, 1200000, 1500000,
                     2000000, 2500000, 3000000, 3500000, 6000000)
    if caps != dict(enumerate(expected_caps, 1)):
        raise ValueError('Flask gauge resource drift')
    bonuses = {}
    for (row,) in source.registrations('SetAccumulatedEDSpecialItem'):
        level = row['ALCHEMIST_LV']
        rewards = row['SPECIAL_REWARD']
        if set(rewards) != {'1'}:
            raise ValueError('Flask bonus resource shape')
        reward = rewards['1']
        bonuses[level] = (reward['1'], reward['2'])
    expected = {level: (109955, level) if level <= 4 else
                (710159, level-4) if level <= 9 else (710084, 1)
                for level in range(1, 11)}
    if bonuses != expected:
        raise ValueError('Flask bonus resource drift')
    return dict(maximum=7, caps=caps, bonuses=bonuses)


def require_alchemist(state):
    from els_server.protocol.profession_messages import state_wire
    state_wire(state)
    if state.profession != 3 or not 1 <= state.level <= 10:
        raise ValueError('Flask requires current alchemist')
    if state.level < 10 and not 0 <= state.progress < state.required:
        raise ValueError('Flask requires a valid saved profession denominator')


def quotation(items, uids, *, now):
    """Local consume exactly one of each of five distinct selected real UIDs."""
    from els_server.domain.npc_sale import unit_price
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    if len(uids) != 5 or len(set(uids)) != 5:
        raise ValueError('Five distinct Flask slots required')
    by_uid = {item['uid']: item for item in items}
    chosen = []
    for uid in uids:
        item = by_uid.get(uid)
        if item is None:
            raise ValueError('Flask input is not an owned inventory instance')
        require_current(item, now=now)
        require_unlocked(item, now=now)
        if item.get('sealed') or item.get('count', 0) < 1:
            raise ValueError('Flask input sealed or empty')
        chosen.append(item)
    total = sum(unit_price(item) for item in chosen)
    if not 0 < total <= 5*(2**31-1):
        raise ValueError('Flask resale sum bound')
    tier = sum(total > boundary for boundary in (1000, 10000, 100000, 200000))
    return dict(resale=total, tier=tier, fee=FEES[tier], units=1,
                quantity=QUANTITIES[tier], xp=min(1000, max(1, total//1000)))


def choose(tier, randbelow):
    weights = WEIGHTS[tier]
    roll = randbelow(sum(weights))
    if type(roll) is not int or not 0 <= roll < sum(weights):
        raise ValueError('Flask RNG bound')
    for template, weight in zip(POOL, weights):
        if roll < weight:
            return {template: QUANTITIES[tier]}
        roll -= weight
    raise ValueError('Flask RNG coverage')


def advance(state, gain):
    """Preserve existing Alchemy denominator/counters and existing next-level curve."""
    require_alchemist(state)
    if type(gain) is not int or not 1 <= gain <= 1000:
        raise ValueError('Flask XP local-policy bound')
    if state.level == 10:
        return state, 0, False
    if state.experience + gain >= 2**31:
        raise ValueError('Flask profession experience overflow')
    from els_server.domain.manufacture_rules import policy
    level, progress, required = state.level, state.progress+gain, state.required
    while level < 10 and progress >= required:
        progress -= required
        level += 1
        required = policy()['level_thresholds'].get(str(level), 0)
    if level == 10:
        progress, required = 0, 0
    return replace(state, level=level, experience=state.experience+gain,
                   progress=progress, required=required), gain, level != state.level
