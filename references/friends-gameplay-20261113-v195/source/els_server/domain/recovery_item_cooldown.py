"""Dungeon recovery-item modifiers from owned, currently worn instances."""

from functools import lru_cache
import json

from els_server.domain.character_stats import equipment_contributes, f32
from els_server.domain.item_expiration import expired


FIELD = 'm_fReduceRecoveryItemCooltime'
LIMIT = f32(.30)


@lru_cache(maxsize=1)
def conversion_rates():
    from els_server.domain.artifact_progression import catalog

    return {
        row['option']: row['native'][FIELD]
        for group in catalog()['conversion']['groups'] for row in group['options']
        if row['native'].get(FIELD) and row['native'].get('DUNGEON_ONLY') == 1
    }


def worn_reduction(db, owner, items, now):
    from els_server.domain.artifact_conversion import validate as artifact_conversion
    from els_server.domain.artifact_progression import require_wearable as artifact_wearable
    from els_server.domain.equipment_circuit_rules import active_slots, catalog as circuits, target as circuit_target
    from els_server.storage.seal_quests import load_character

    sources = [
        item for item in items
        if (item['group'] == 9 and item.get('option_groups', {}).get('28')
            or item['group'] == 24 and item.get('option_groups', {}).get('31'))
        and not expired(item, now=now) and item.get('identified') is not False
        and not item.get('sealed', False)
    ]
    if not sources:
        return 0.0

    character = load_character(db, owner, identity_only=True)
    # Native 8A2430 enables circuit callbacks only when all four worn armor
    # positions carry property 0x50. The pinned targets are exactly that set.
    armor = {}
    if any(item['group'] == 9 for item in sources):
        for item in items:
            if item['group'] != 9:
                continue
            target = circuit_target(item['template'])
            if (target and not expired(item, now=now) and item.get('identified') is not False
                and not item.get('sealed', False) and equipment_contributes(item, character)):
                armor[target['part']] = item['uid']
    active_circuit_owners = set(armor.values()) if len(armor) == 4 else set()
    if character['master'] and any(item['group'] == 24 for item in sources):
        artifact = db.execute(
            'SELECT template,evolution,level,experience,potentials FROM character_artifacts WHERE uid=?',
            (owner,),
        ).fetchone()
        if artifact:
            character['artifact'] = dict(
                template=artifact[0], evolution=artifact[1], level=artifact[2],
                experience=artifact[3], potentials=json.loads(artifact[4]),
            )
    total = 0.0
    for item in sources:
        groups = item['option_groups']
        if item['group'] == 9:
            if item['uid'] not in active_circuit_owners:
                continue
            grid = groups['28']
            options = circuits()['options']
            for position in active_slots(item['template'], grid):
                row = options[str(grid[position])]
                if row.get(FIELD) and row.get('DUNGEON_ONLY') == 1:
                    # Native 9859A0 adds this field outside the weighted block.
                    total = f32(total + f32(row[FIELD]))
        elif character.get('artifact'):
            artifact_wearable(item, character)
            for option in artifact_conversion(item['template'], groups['31']):
                total = f32(total + f32(conversion_rates().get(option, 0.0)))
    return total
