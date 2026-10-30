"""Which admitted dungeon routes can grant their native Boss drop, and what blocks the rest.

Four independent gates decide whether a cleared Boss can actually hand the player
the item DungeonData.lua declares for that dungeon. Every gate below is read
through the same function the runtime uses; nothing is re-derived here, so a
policy or evidence change moves this report instead of silently diverging.

  1. route admission        route_catalog()          - the map has a captured solo graph
  2. native declaration     DungeonData.lua           - BOSS_DROP_ITEM names the template
  3. acquisition policy     can_acquire()             - the template may be newly granted
  4. instance descriptor    an existing item catalog  - the class has native ground/inventory evidence

Gate 4 is the one people forget. An item template that passes gate 3 still needs
a catalog entry that knows its instance shape (equipment type1/2 default, material
type6/7, accessory type3). Without that, a grant would have to invent the body
bytes the client decodes, which is exactly what this project refuses to do.

Usage:
  python tools/loot_scope_report.py [--json] [--map 34000] [--limit N]
"""
import argparse, collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _native_boss_drops():
    """dungeonID -> sorted native BOSS_DROP_ITEM templates, every class bucket."""
    from els_server.game_data import client_data

    drops = {}
    for call in client_data().resource('DungeonData.lua')['__symbolic_calls__']:
        target = call.get('function')
        name = target.get('global') if isinstance(target, dict) else target
        if name != 'g_pDungeonManager.AddDungeonData':
            continue
        arguments = call.get('arguments') or []
        if len(arguments) < 2 or not isinstance(arguments[1], dict):
            continue
        row = arguments[1]
        identity = row.get('dungeonID')
        declared = row.get('BOSS_DROP_ITEM')
        if identity is None or not isinstance(declared, dict):
            continue
        members = set()
        for bucket in declared.values():
            if isinstance(bucket, dict):
                members.update(v for v in bucket.values() if type(v) is int and v > 0)
        if members:
            drops[identity] = sorted(members)
    return drops


def _admitted():
    from els_server.domain.dungeon_routes import route_catalog

    return {int(k) for k in route_catalog()._data['routes']}


def _catalogs():
    """Existing instance-descriptor catalogs, keyed by the class they describe."""
    from els_server.domain import dungeon_equipment_loot_flow as flow
    from els_server.domain.dungeon_equipment_loot_rules import LEGACY_TEMPLATES
    from els_server.domain.dungeon_loot_catalog import MAPS as NORMAL_MAPS, TEMPLATES as NORMAL
    from els_server.domain.dungeon_material_loot_catalog import MAPS as MATERIAL_MAPS, TEMPLATES as MATERIAL
    from els_server.domain.dungeon_source_loot import MAPS as SOURCE_MAPS, TEMPLATES as SOURCE

    return dict(
        covered=flow.MAPS | NORMAL_MAPS | MATERIAL_MAPS | SOURCE_MAPS,
        templates={
            'normal-equipment-default-v1': frozenset(NORMAL),
            'ordinary-material-default-v1': frozenset(MATERIAL),
            'legacy-source-compatibility-v1': frozenset(SOURCE),
            'equipment-fragment-v1': frozenset(LEGACY_TEMPLATES),
        },
    )


def _descriptor_for(template, catalogs):
    for kind, members in catalogs['templates'].items():
        if template in members:
            return kind
    return None


def _blocked_reason(template):
    """Why can_acquire() refuses this template, in the policy's own vocabulary.

    can_acquire() answers False; require_acquirable() is the raising wrapper.
    Read the boolean, not the absence of an exception.
    """
    from els_server.domain.acquisition_policy import (can_acquire, excluded_equipment,
                                                      CARTRIDGE_USE_ONLY_MATERIALS,
                                                      HISTORICAL_PAGE1_USE_ONLY_TICKETS,
                                                      LEGACY_USE_ONLY_TICKETS,
                                                      LITHIA_GEN7_USE_ONLY_TICKETS)
    from els_server.domain.ordinary_accessories import definitions
    from els_server.game_data import client_data

    if can_acquire(template):
        return None
    if template in excluded_equipment():
        return 'legacy_marker'
    accessory = definitions().get(template)
    if accessory is not None and accessory['compatibility_only']:
        return 'accessory_compatibility_only'
    from els_server.domain.raid_reward_items import source_only_templates

    if template in source_only_templates():
        return 'raid_source_only'
    if template in CARTRIDGE_USE_ONLY_MATERIALS:
        return 'cartridge_use_only'
    for name, members in (('legacy_ticket_use_only', LEGACY_USE_ONLY_TICKETS),
                          ('lithia_gen7_ticket_use_only', LITHIA_GEN7_USE_ONLY_TICKETS),
                          ('historical_page1_use_only', HISTORICAL_PAGE1_USE_ONLY_TICKETS)):
        if template in members:
            return name
    try:
        item_type = client_data().item(template)['item_type']
    except Exception:
        return 'unknown_template'
    return f'policy_blocked_type_{item_type}'


def report():
    from els_server.game_data import client_data

    data = client_data()
    drops = _native_boss_drops()
    admitted = _admitted()
    catalogs = _catalogs()
    covered = admitted & catalogs['covered']
    uncovered = sorted(admitted - catalogs['covered'])

    buckets = collections.Counter()
    reasons = collections.Counter()
    classes = collections.Counter()
    rows = []
    for identity in uncovered:
        members = drops.get(identity, [])
        verdict = {t: _blocked_reason(t) for t in members}
        grantable = [t for t in members if verdict[t] is None]
        blocked = [(t, verdict[t]) for t in members if verdict[t] is not None]
        for _, reason in blocked:
            reasons[reason] += 1
        reusable = [(t, _descriptor_for(t, catalogs)) for t in grantable if _descriptor_for(t, catalogs)]
        for t in members:
            try:
                classes[data.item(t)['item_type']] += 1
            except Exception:
                classes['unknown'] += 1
        if not members:
            bucket = 'no_native_drop'
        elif reusable:
            bucket = 'reusable_descriptor'
        elif grantable:
            bucket = 'needs_class_evidence'
        else:
            bucket = 'policy_blocked'
        buckets[bucket] += 1
        reusable_templates = [r[0] for r in reusable]
        rows.append(dict(
            dungeon=identity,
            bucket=bucket,
            native_members=members,
            reusable=[dict(template=t, descriptor=kind) for t, kind in reusable],
            grantable_but_undescribed=[t for t in grantable if t not in reusable_templates],
            blocked=[dict(template=t, reason=r) for t, r in blocked],
        ))

    return dict(
        schema_version=1,
        admitted=len(admitted),
        covered=len(covered),
        uncovered=len(uncovered),
        buckets=dict(sorted(buckets.items())),
        blocked_reasons=dict(sorted(reasons.items())),
        native_member_item_types=dict(sorted((str(k), v) for k, v in classes.items())),
        maps=rows,
    )


def _print_human(data, limit):
    print(f'admitted routes : {data["admitted"]}')
    print(f'already rewarded: {data["covered"]}')
    print(f'uncovered       : {data["uncovered"]}')
    print()
    print('buckets over the uncovered maps:')
    for key, value in data['buckets'].items():
        print(f'  {value:>4}  {key}')
    print()
    print('why can_acquire() refuses a declared template:')
    if not data['blocked_reasons']:
        print('  (none)')
    for key, value in data['blocked_reasons'].items():
        print(f'  {value:>4}  {key}')
    print()
    print('declared template item_type histogram (references, not distinct items):')
    for key, value in data['native_member_item_types'].items():
        print(f'  {value:>4}  type {key}')
    print()
    shown = 0
    for row in data['maps']:
        if row['bucket'] == 'no_native_drop':
            continue
        if shown >= limit:
            break
        shown += 1
        if row['reusable']:
            detail = 'reusable=' + ','.join(f'{r["template"]}@{r["descriptor"]}' for r in row['reusable'])
        elif row['grantable_but_undescribed']:
            detail = 'grantable-but-undescribed=' + str(row['grantable_but_undescribed'])
        else:
            detail = 'blocked=' + ','.join(f'{b["template"]}({b["reason"]})' for b in row['blocked'])
        print(f'  {row["dungeon"]:<7} {row["bucket"]:<24} {detail}')
    remaining = sum(1 for r in data['maps'] if r['bucket'] != 'no_native_drop') - shown
    if remaining > 0:
        print(f'  ... {remaining} more (raise --limit)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='emit the raw report')
    parser.add_argument('--map', type=int, help='only this dungeon id')
    parser.add_argument('--limit', type=int, default=25, help='human rows to print')
    args = parser.parse_args()

    data = report()
    if args.map is not None:
        row = next((r for r in data['maps'] if r['dungeon'] == args.map), None)
        print(json.dumps(row if row is not None else dict(dungeon=args.map, error='not uncovered'),
                         ensure_ascii=False, indent=2))
        return
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    _print_human(data, args.limit)


if __name__ == '__main__':
    main()
