"""Small saved-field groups for existing complete Unit producers.

The caller owns the connection, transaction, identity checks and field order.
These helpers never open a connection or assemble an eligibility/full-role DTO.
Roster omission of empty traits and single pages is deliberately explicit;
quest refreshes retain those keys even when their saved values are empty.
"""


def skill_trait_fields(db, character, *, include_empty):
    from els_server.storage.skill_traits import saved as saved_traits
    from els_server.domain.skill_traits import visible as visible_traits
    traits = saved_traits(db, character['uid'])
    if traits or include_empty:
        return {'skill_traits': visible_traits(character, traits)}
    return {}


def force_fields(db, uid):
    from els_server.storage.boosting_2026_force_inventory import saved as saved_inventory
    from els_server.storage.boosting_2026_force_equipment import saved as saved_slots
    return {'force_inventory': saved_inventory(db, uid),
            'force_slots': saved_slots(db, uid)}


def skill_page_fields(db, uid, *, include_single):
    from els_server.storage.ordinary_skill_pages import view as skill_pages_view
    pages = skill_pages_view(db, uid)
    return {'ordinary_skill_pages': pages} if include_single or pages['count'] > 1 else {}


def cleared_dungeons(db, uid, *, has_records):
    return tuple(row[0] for row in db.execute(
        'SELECT map_id FROM dungeon_records WHERE uid=? ORDER BY map_id', (uid,))) if has_records else ()


def profession_fields(db, uid, account_id):
    from els_server.storage.profession_state import snapshot as profession_snapshot
    profession = profession_snapshot(db, uid, account_id)
    return {'profession': profession['state'], 'profession_revision': profession['revision']}
