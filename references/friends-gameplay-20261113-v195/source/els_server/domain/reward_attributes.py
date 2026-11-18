"""Read saved character sources inside the authoritative reward transaction."""
from decimal import Decimal
from functools import lru_cache
import json

from els_server.domain.title_option_data import catalog

ED = 'm_fIncreaseEDPercent'
EXP = 'm_fIncreaseDCBExpPercent'
DROP = 'm_fIncreaseItemDropRate'
ATMA_OPTIONS = frozenset({100920017, 100920018, 100920019})


@lru_cache(maxsize=1)
def option_rates():
    return {
        key: {field: int(Decimal(str(row[field])) * 10000)
              for field in (ED, EXP, DROP) if row.get(field)}
        for key, row in catalog().items() if any(row.get(field) for field in (ED, EXP, DROP))
    }


@lru_cache(maxsize=1)
def resonance_rules():
    from els_server.domain.resonance_allocation_flow import definitions
    _, raw = definitions()
    return raw, {row['stat_id']: (row['maximum'], int(row['per_point'] * 100))
                 for row in json.loads(raw)['rows'] if row['stat_id'] in (13, 14, 15)}


def resonance_bonus(db, owner, stat, now):
    from els_server.storage.titles import exists
    if not exists(db, 'resonance2026_characters'):
        return 0
    from els_server.storage.resonance_state import snapshot
    progress = snapshot(db, owner)
    if not progress['enabled']:
        return 0
    account = progress['account_id']
    from els_server.storage.resonance_2026_pages import ResonancePages
    raw, rates = resonance_rules()
    pages = ResonancePages(db, raw).read(account, owner)
    if pages is None or not pages.enabled:
        return 0
    points = dict(pages.selected().points).get(stat, 0)
    from els_server.storage.resonance_period import active
    period = active(db, account, owner, now=now)
    if period and period[0] == stat:
        points += period[1]
    maximum, per_point = rates[stat]
    return min(points, maximum) * per_point


def gear_bonus(db, owner, fields, now):
    from els_server.storage.titles import exists
    from els_server.storage.character_custom import snapshot as custom_snapshot
    from els_server.domain.equipment_spell_rules import capacity
    from els_server.domain.ordinary_accessories import definitions, accepts_equipped
    from els_server.domain.character_stats import equipment_contributes
    from els_server.domain.equipment_requirements import class_matches
    from els_server.domain.item_expiration import expired
    from els_server.game_data import client_data
    from els_server.storage.inventory_state import load_equipped_items

    total = dict.fromkeys(fields, 0)
    sources = option_rates()
    identity = db.execute('SELECT unit_type,unit_class,level FROM characters WHERE uid=?', (owner,)).fetchone()
    if identity is None:
        return total
    character = dict(zip(('unit_type', 'unit_class', 'level'), identity))
    side = 0
    if character['unit_type'] == 10:
        from els_server.storage.luciel_state import state, active_state
        from els_server.domain.tutorial_accessory import effective_style
        character.update(luciel_style=state(db, owner)['style'],
                         luciel_active_unit=active_state(db, owner)['active_unit'])
        side = effective_style(character)

    if exists(db, 'equipment_options'):
        for item in load_equipped_items(db, owner):
            groups = item.get('option_groups', {})
            if item['group'] != 9 or not groups or expired(item, now=now) or item.get('identified') is False:
                continue
            mystic = {group: groups[group] for group in ('9', '10', '11', '12')
                      if any(key in sources for key in groups.get(group, ()))}
            ids = []
            if mystic and equipment_contributes(item, character):
                for group, keys in mystic.items():
                    ids.extend(keys[:capacity(item, int(group))])
            accessory = ATMA_OPTIONS.intersection(groups.get('1', ()))
            if accessory:
                template = item['template']
                if (accepts_equipped(item) and item.get('identified') is True
                    and int(item['slot'] not in definitions()[template]['main_slots']) == side
                    and class_matches(character['unit_class'], client_data().item(template)['record'][0xd3])):
                    ids.extend(accessory)
            for key in ids:
                for field in fields:
                    total[field] += sources.get(key, {}).get(field, 0)

    if exists(db, 'character_custom_permanent_abilities'):
        selected = custom_snapshot(db, owner, now)['selected']
        # A saved custom ID can occupy multiple animation slots.
        for key in {row['custom_id']: row['ability'] for row in selected.values()}.values():
            for field in fields:
                total[field] += sources.get(key, {}).get(field, 0)
    return total


@lru_cache(maxsize=1)
def greed_base_rates():
    from els_server.game_data import client_data
    definition = client_data().skill(900407)
    base = next(row for key, row in definition.items()
                if key.startswith('NUMERICAL_DATA') and row['m_wstrName'] == 'SA_DROP_REL')
    return {int(rank): int(Decimal(str(rate)) * 100)
            for rank, rate in base['m_Value'].items() if rate is not None}


def greed_bonus(db, owner):
    from els_server.storage.titles import exists
    if not exists(db, 'selected_2026_force_slots'):
        return 0
    if not db.execute('SELECT 1 FROM selected_2026_force_slots WHERE owner=? AND skill=900407 AND slot<3',
                      (owner,)).fetchone():
        return 0
    from els_server.storage.boosting_2026_force_equipment import _character
    from els_server.domain.boosting_2026_force_equipment import slots
    from els_server.storage.bank_state import account_for
    character = _character(db, owner, account_for(db, owner))
    if character['level'] < 99:
        return 0
    # The native fixed term applies independently of the intermediate CP.
    return next((greed_base_rates()[rank] for skill, rank in slots(character, visible=True)[:3]
                 if skill == 900407), 0)
