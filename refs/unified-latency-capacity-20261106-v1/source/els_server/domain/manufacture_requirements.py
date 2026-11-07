"""Checked crafting prerequisites, not recipe authorization or a transaction.

Native evidence: manufacture-requirements-native.json and
manufacture-material-native.json. Output probabilities, selected/auxiliary UID
semantics, profession/availability/limit rules and fee waivers remain separate.
"""
from collections import Counter
from els_server.manufacture_data import manufacture_data

I32_MAX = 2**31-1
EXCLUDED_GROUPS = frozenset((8, 9, 11, 13, 14, 16, 22, 23, 24, 26, 28))
SPECIAL_COUNTER_MATERIALS = frozenset((100002375, 100002436))


def inspect_limit(*, maximum, used, quantity):
    """Read-only quota arithmetic for explicit state, without resetting it.

    Native2319000 clamps maximum-used to [0,maximum]. Missing state must be
    resolved by the caller; the client's missing-entry allow is not authority.
    This helper neither establishes the period/owner nor reserves capacity.
    """
    for name, value in (('maximum', maximum), ('used', used)):
        if type(value) is not int or not 0 <= value <= I32_MAX:
            raise ValueError('Manufacture limit ' + name)
    if type(quantity) is not int or not 1 <= quantity <= I32_MAX:
        raise ValueError('Manufacture quantity')
    remaining = max(0, maximum-used)
    return dict(maximum=maximum, used=used, remaining=remaining,
                quantity=quantity, fits=quantity <= remaining,
                transaction_implemented=False)


def inspect_profession(recipe_id, state):
    """Compare an explicit profession snapshot; does not authorize crafting.

    The caller must obtain owner-scoped current state and recheck it within
    the eventual transaction. Missing state is not a no-requirement recipe.
    """
    from els_server.protocol.profession_messages import state_wire
    state_wire(state)
    definition = manufacture_data().recipe(recipe_id)['definition']
    required = definition.get('m_RequireProfessionType', 0)
    minimum = definition.get('m_LimitProfessionLevel', 0)
    if (type(required) is not int or not 0 <= required <= 3
            or type(minimum) is not int or not 0 <= minimum <= 255
            or bool(required) != bool(minimum)):
        raise ValueError('Unsupported manufacture profession requirement')
    active = required != 0
    return dict(recipe_id=recipe_id,required_profession=required,minimum_level=minimum,
                has_requirement=active,
                satisfied=active and state.profession == required and state.level >= minimum,
                fits=not active or (state.profession == required and state.level >= minimum),
                transaction_implemented=False)


def require_output_references(recipe_id):
    """Reject unresolved or forbidden candidates without filtering the pool.

    This validates references and the owner's acquisition policy only. Even
    one unique candidate does not prove its quantity, probability or inherited
    fields. Keep registrations in their original order, including duplicates.
    """
    from els_server.game_data import client_data
    from els_server.domain.acquisition_policy import require_acquirable
    candidates = manufacture_data().recipe(recipe_id)['result_registrations']
    if not isinstance(candidates, list) or not candidates:
        raise ValueError('Manufacture result group missing')
    if any(type(t) is not int or not 1 <= t <= I32_MAX for t in candidates):
        raise ValueError('Manufacture result identity')
    identities = sorted(set(candidates))
    with client_data().connect() as db:
        known = {row[0] for row in db.execute(
            'SELECT id FROM items WHERE id IN (' + ','.join('?' for _ in identities) + ')',
            identities)}
    if known != set(identities):
        raise ValueError('Manufacture result definition missing')
    for template in identities:
        require_acquirable(template)
    return tuple(candidates)


def requirements(recipe_id, quantity=1):
    """Ordinary base fee and aggregated material demand, with no i32 wrapping."""
    if type(quantity) is not int or not 1 <= quantity <= I32_MAX:
        raise ValueError('Manufacture quantity')
    recipe = manufacture_data().recipe(recipe_id)['definition']
    cost = recipe['m_Cost']
    if type(cost) is not int or not 0 <= cost <= I32_MAX:
        raise ValueError('Unsupported manufacture cost')
    demand = Counter()
    for row in recipe['m_MaterialTable'].values():
        template, count = row['m_MaterialID'], row['m_MaterialCount']
        if (type(template) is not int or not 1 <= template <= I32_MAX
                or template in SPECIAL_COUNTER_MATERIALS
                or type(count) is not int or not 1 <= count <= I32_MAX):
            raise ValueError('Unsupported manufacture material')
        demand[template] += count*quantity
        # Native count/requirement consumers are signed32. Never reproduce
        # the client overflow, including repeated rows for the same material.
        if demand[template] > I32_MAX:
            raise ValueError('Manufacture material quantity overflow')
    # Native23152FA sets the UI map marker from (flags4 >>24)&15 ==2;
    # 2316DF5 omits such entries from the auxiliary UID set. All quantities
    # remain required. Missing legacy definitions remain explicitly unknown.
    from els_server.game_data import client_data
    metadata = {}
    if demand:
        with client_data().connect() as db:
            metadata = dict(db.execute('SELECT id,metadata FROM items WHERE id IN ('
                                       + ','.join('?' for _ in demand) + ')',tuple(demand)))
    modes = {t:('unknown_definition' if t not in metadata else
                'omitted_by_client' if metadata[t] == 2 else 'instance_candidate') for t in sorted(demand)}
    return dict(recipe_id=recipe_id, quantity=quantity, base_ed=cost*quantity,
                materials=dict(sorted(demand.items())), auxiliary_uid_modes=modes,transaction_implemented=False,
                scope='Base requirements only; does not authorize crafting, quote fee waivers or determine outputs.')


def inventory_candidates(items, *, now):
    """Current server-schema candidates; caller must supply owner-scoped items.

This does not select or reserve consumption UIDs. Native byte58 is the sealed
flag and is checked here. Other native reservation/event fields absent from
the current server schema use the explicitly authorized default-instance
compatibility policy. Expiration is checked in addition to native197ED40.
"""
    from els_server.domain.inventory_items import validate_item
    from els_server.domain.item_locks import locked
    from els_server.domain.item_expiration import expired
    if type(now) is not int or now < 0:
        raise ValueError('Manufacture inventory clock')
    if not isinstance(items, (list, tuple)):
        raise ValueError('Manufacture inventory collection')
    seen, slots, result = set(), set(), {}
    for raw in items:
        item = validate_item(raw)
        position = item['group'], item['slot']
        if item['uid'] in seen or position in slots:
            raise ValueError('Duplicate manufacture inventory identity/slot')
        seen.add(item['uid']); slots.add(position)
        if item['group'] in EXCLUDED_GROUPS or item.get('sealed',False) or locked(item, now=now) or expired(item, now=now):
            continue
        result.setdefault(item['template'], []).append((item['uid'], item['count']))
    # Canonical presentation only, NOT a rule to consume the smallest UID first.
    return {template:tuple(sorted(entries)) for template,entries in sorted(result.items())}


def inspect_request(payload, items, *, now):
    """Preflight declared UIDs against owner-scoped current-schema candidates.

No fallback UID substitution or consumption plan: an invalid explicit selection
fails even when other stacks could satisfy the recipe. Caller must reload and
revalidate ownership inside the eventual transaction; this is read-only.
"""
    from els_server.protocol.manufacture_messages import manufacture_request
    request = manufacture_request(payload)
    result = requirements(request.recipe_id, request.quantity)
    result['output_candidates'] = require_output_references(request.recipe_id)
    result['output_rules_verified'] = False
    candidates = inventory_candidates(items, now=now)
    by_uid = {uid:template for template,entries in candidates.items() for uid,_ in entries}
    declared = (() if request.selected_uid == -1 else (request.selected_uid,)) + request.auxiliary_uids
    for uid in declared:
        if uid not in by_uid:
            raise ValueError('Selected manufacture UID is missing or unavailable')
        if by_uid[uid] not in result['materials']:
            raise ValueError('Selected manufacture UID is not a recipe material')
    available = {t:sum(count for _,count in candidates.get(t,())) for t in result['materials']}
    result.update(selected_uid=request.selected_uid,auxiliary_uids=request.auxiliary_uids,
                  available=available,
                  shortages={t:needed-available[t] for t,needed in result['materials'].items()
                             if needed>available[t]})
    return result
