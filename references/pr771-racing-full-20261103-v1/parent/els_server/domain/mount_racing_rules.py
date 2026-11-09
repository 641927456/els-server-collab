"""User-authorized local racing policy; probabilities are not retail claims.

These calculations do not accept network requests or establish a race result.
The race controller must own admission, stamina charging and the finish order.
"""
import bisect
import functools
import json
import secrets
from els_server.paths import PROJECT_ROOT


@functools.lru_cache(maxsize=1)
def policy():
    p = json.loads((PROJECT_ROOT/'els_server/data/mount_racing_local.json').read_bytes())
    curve = p['cumulative_experience']
    increments = p['points_on_level']
    if (p['schema_version'] != 1 or p['provenance'] != 'local_policy'
            or p['policy'] != 'pr771-local-mount-racing-v1'):
        raise ValueError('Mount racing policy provenance')
    if (len(curve) != p['maximum_level'] or len(increments) != len(curve)
            or curve[0] != 0 or curve[-1] != 11300
            or any(type(n) is not int or n < 0 for n in curve+increments)
            or any(a >= b for a, b in zip(curve, curve[1:]))
            or increments[0] != 0 or sum(increments) != 30
            or p['attribute_ids'] != [0, 1, 2, 3] or p['attribute_cap'] != 10
            or p['allocation'] != 'uniform_among_attributes_below_cap'
            or len(p['rank_experience']) != 6
            or any(type(n) is not int or n < 0 for n in p['rank_experience'])
            or set(p['bonus_weights_by_rank']) != {'1', '2', '3'}
            or p['bonus_reward_types'] != list(range(12))
            or p['experience_multiplier_percent'] != [110, 120, 130, 150, 200, 300]):
        raise ValueError('Mount racing growth policy')
    for weights in p['bonus_weights_by_rank'].values():
        if (len(weights) != 12 or sum(weights) != 100
                or any(type(w) is not int or w < 0 for w in weights)):
            raise ValueError('Mount racing reward weights')
    return p


def level(experience):
    curve = policy()['cumulative_experience']
    if type(experience) is not int or not 0 <= experience <= curve[-1]:
        raise ValueError('Mount racing experience range')
    return bisect.bisect_right(curve, experience)


def points(experience):
    return sum(policy()['points_on_level'][:level(experience)])


def allocate(stats, count, randbelow=secrets.randbelow):
    p = policy()
    if (not isinstance(stats, dict)
            or any(type(k) is not int or k not in p['attribute_ids'] for k in stats)):
        raise ValueError('Mount racing attribute IDs')
    result = {i: stats.get(i, 0) for i in p['attribute_ids']}
    if (type(count) is not int or count < 0
            or any(type(v) is not int or not 0 <= v <= p['attribute_cap'] for v in result.values())
            or count > p['attribute_cap']*4-sum(result.values())):
        raise ValueError('Mount racing attribute allocation')
    for _ in range(count):
        pool = [i for i in p['attribute_ids'] if result[i] < p['attribute_cap']]
        roll = randbelow(len(pool))
        if type(roll) is not int or not 0 <= roll < len(pool):
            raise ValueError('Mount racing random source')
        result[pool[roll]] += 1
    return {i: v for i, v in result.items() if v}


def profile(experience=0, stats=None):
    current_level = level(experience)
    normalized = allocate({} if stats is None else stats, 0)
    if sum(normalized.values()) != points(experience):
        raise ValueError('Mount racing saved point count')
    return dict(level=current_level, experience=experience, stats=normalized)


def grow(experience, stats, amount, randbelow=secrets.randbelow):
    saved = profile(experience, stats)
    if type(amount) is not int or amount < 0:
        raise ValueError('Mount racing experience award')
    new = min(policy()['cumulative_experience'][-1], experience+amount)
    return dict(level=level(new), experience=new,
                stats=allocate(saved['stats'], points(new)-points(experience), randbelow))


def reset(experience, stats, randbelow=secrets.randbelow):
    saved = profile(experience, stats)
    if saved['level'] < policy()['reset_minimum_level']:
        raise ValueError('Mount racing reset requires earned points')
    return dict(saved, stats=allocate({}, points(experience), randbelow))


def reward(rank, lanes, randbelow=secrets.randbelow):
    p = policy()
    if (type(rank) is not int or type(lanes) is not int
            or not 3 <= lanes <= 6 or not 1 <= rank <= lanes):
        raise ValueError('Mount racing result rank')
    amount = p['rank_experience'][rank-1]
    kind, item = -1, None
    if lanes == p['bonus_required_lanes'] and str(rank) in p['bonus_weights_by_rank']:
        roll = randbelow(100)
        if type(roll) is not int or not 0 <= roll < 100:
            raise ValueError('Mount racing random source')
        for kind, weight in enumerate(p['bonus_weights_by_rank'][str(rank)]):
            if roll < weight:
                break
            roll -= weight
        if kind < 6:
            amount = amount*p['experience_multiplier_percent'][kind]//100
        elif kind < 11:
            item = dict(template=p['fragment_template'], quantity=kind-5)
        else:
            item = dict(template=p['crystal_template'], quantity=1)
    return dict(experience=amount, bonus_type=kind, item=item)


def result(experience, stats, rank, lanes, randbelow=secrets.randbelow):
    """Calculate one trusted finish; caller persists/grants once per race ID."""
    saved = profile(experience, stats)
    awarded = reward(rank, lanes, randbelow)
    updated = grow(saved['experience'], saved['stats'], awarded['experience'], randbelow)
    return dict(profile=updated, reward=awarded,
                experience_gained=updated['experience']-experience)
