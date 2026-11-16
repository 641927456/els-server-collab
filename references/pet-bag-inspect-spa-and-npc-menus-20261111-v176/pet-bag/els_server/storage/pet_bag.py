"""Character-owned pet inventory, with atomic transfers of existing instances."""
import json
import sqlite3
import struct
from contextlib import closing

from els_server.domain.bag_capacity import BAG_GROUPS
from els_server.domain.cartridge_registration_rules import non_authority, require_unbound
from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS, validate_item
from els_server.domain.item_expiration import expired, require_current
from els_server.domain.item_locks import locked, require_unlocked
from els_server.domain.pet_progression import catalog, template
from els_server.game_data import client_data
from els_server.protocol import pet_bag_messages as wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.bag_capacity import allowances
from els_server.storage.equipment_chip_reset_history import hydrate, legacy
from els_server.storage.inventory_actions import _commit, _identity, _previous
from els_server.storage.inventory_state import load_items
from els_server.storage.item_actor import require_active_character
from els_server.storage.item_instances import bag_group, insert, read_stored, reduce_count, relocate, remove
from els_server.storage.pet_support import owned_pet
from els_server.storage.profession_state import require_owner
from els_server.storage.read_scope import snapshot_connection
from els_server.storage.sqlite_timing import write_transaction


def _eligible_pet(db, owner, account_id, pet_uid):
    require_owner(db, owner, account_id)
    require_active_character(db, owner)
    pet = owned_pet(db, owner, pet_uid)
    from els_server.storage.housing_pets import require_available
    require_available(db, owner, pet_uid)
    capacity = _capacity(pet)
    if capacity == 0:
        raise ValueError('Pet has no usable storage slots')
    return pet, capacity


def _capacity(pet):
    stage = str(pet['step'] + 1)
    definition = template(pet['unit'])
    capacity = definition['INVENSLOT_WIDTH_SIZE'][stage] * definition['INVENSLOT_HEIGHT_SIZE'][stage]
    if not 0 <= capacity <= wire.SLOTS:
        raise ValueError('Invalid pet storage capacity')
    return capacity


def _require_deposit(item):
    definition = client_data().item(item['template'])
    # Native pet drag 2249E21 checks bit 5. 224A06C..224A09D also
    # reject the instance period and the template's deadline string (KIM +64h).
    if definition['flags4'] & 32:
        raise ValueError('Original item definition forbids pet storage')
    if ('expires_at' in item or 'activation_seconds' in item
        or struct.unpack_from('<I', definition['record'], 0x64)[0]):
        raise ValueError('Time-limited item cannot enter pet storage')


def _contents(db, owner, pet_uid, capacity):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='pet_bag_items' AND type='table'").fetchone():
        return {}
    contents = {}
    rows = db.execute('SELECT uid, slot, item_json FROM pet_bag_items WHERE owner=? AND pet=? ORDER BY slot',
                      (owner, pet_uid))
    for uid, slot, raw in rows:
        item = hydrate(db, validate_item(read_stored(non_authority(json.loads(raw)))))
        if item['uid'] != uid or item['group'] != bag_group(item) or not 0 <= slot < capacity:
            raise ValueError('Pet bag instance and slot mismatch')
        require_unbound(db, uid)
        contents[slot] = item
    return contents


def select(path, owner, account_id, pet_uid, guard):
    with snapshot_connection(path) as db:
        db.execute('BEGIN')
        guard(db)
        pet, capacity = _eligible_pet(db, owner, account_id, pet_uid)
        contents = _contents(db, owner, pet_uid, capacity)
        answer = wire.selected(pet, [(slot, item) for slot, item in contents.items() if not expired(item)])
        encode_event(answer)
        guard(db)
        return answer


def set_auto_feed(path, owner, account_id, pet_uid, enabled, guard):
    from els_server.storage.pet_progression import save
    with closing(sqlite3.connect(path, timeout=10)) as db, write_transaction(db):
        guard(db)
        pet, _ = _eligible_pet(db, owner, account_id, pet_uid)
        if pet['auto_feed'] != enabled:
            pet['auto_feed'] = enabled
            save(db, owner, pet)
        answer = wire.auto_feed_setting(pet_uid, enabled)
        encode_event(answer)
        guard(db)
        return answer


def auto_feed(db, owner, pet):
    # Current satiety is stored in 4800ths. Only the summoned pet's confirmed
    # special foods participate in the automatic selection.
    if not pet['auto_feed'] or pet['satiety'] >= 3840:
        return None
    capacity = _capacity(pet)
    if capacity == 0:
        return None
    rules = catalog()
    choices = []
    for slot, item in _contents(db, owner, pet['uid'], capacity).items():
        template_id = item['template']
        if (template_id not in rules['special_feed_ids'] or template_id in rules['restricted']
            or str(template_id) not in rules['feeds'] or expired(item) or locked(item)
            or item.get('sealed', False)):
            continue
        # Use the current food's native grade and the pet slot as a tie-breaker.
        grade = (client_data().item(template_id)['flags4'] >> 20) & 15
        choices.append((-grade, slot, item))
    if not choices:
        return None

    _, slot, item = min(choices)
    from els_server.storage.pet_progression import apply_food
    apply_food(pet, item['template'], rules['feeds'][str(item['template'])],
               rules['nutrients'].get(str(item['template']), {}).get('points', 0))
    remaining = reduce_count(item, item['count'] - 1) if item['count'] > 1 else None
    answer = wire.auto_fed(pet, item['template'], slot, remaining)
    encode_event(answer)
    if remaining is None:
        db.execute('DELETE FROM pet_bag_items WHERE owner=? AND pet=? AND slot=?',
                   (owner, pet['uid'], slot))
    else:
        db.execute('UPDATE pet_bag_items SET item_json=? WHERE owner=? AND pet=? AND slot=?',
                   (json.dumps(remaining, sort_keys=True), owner, pet['uid'], slot))
    return answer


def move(path, owner, account_id, pet_uid, payload, operation, guard):
    sg, ss, dg, ds, flag = struct.unpack('>BiBiB', payload)
    source, destination = (sg, ss), (dg, ds)
    if (flag or source == destination or wire.GROUP not in (sg, dg)
        or any(g != wire.GROUP and g not in BAG_GROUPS for g in (sg, dg))):
        raise ValueError('Invalid pet bag move positions')
    owner, digest = _identity(owner, 0x104, struct.pack('>Q', pet_uid) + payload, operation)
    with closing(sqlite3.connect(path, timeout=10)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        with write_transaction(db):
            guard(db)
            _, capacity = _eligible_pet(db, owner, account_id, pet_uid)
            limits = allowances(db, owner)
            limits[wire.GROUP] = capacity
            if any(not 0 <= slot < limits[group] for group, slot in (source, destination)):
                raise ValueError('Pet bag move slot is out of bounds')

            contents = _contents(db, owner, pet_uid, capacity)
            items = {(item['group'], item['slot']): item for item in load_items(db, owner)}
            items.update({(wire.GROUP, slot): item for slot, item in contents.items() if not expired(item)})
            prior = _previous(db, operation, digest)
            if prior is not None:
                answer = wire.moved([(point, items.get(point)) for point in prior])
                encode_event(answer)
                guard(db)
                return answer

            first, second = items.get(source), items.get(destination)
            if first is None:
                raise ValueError('Pet bag move source is empty')

            return_position = source
            if second is not None and dg == wire.GROUP and sg != wire.GROUP:
                return_group = bag_group(second)
                if return_group != sg:
                    return_slot = next((slot for slot in range(limits[return_group])
                                        if (return_group, slot) not in items), None)
                    if return_slot is None:
                        raise ValueError('Pet bag swap requires a free slot in the outgoing item tab')
                    return_position = (return_group, return_slot)

            for item, origin, target in ((first, source, destination), (second, destination, return_position)):
                if item is None:
                    continue
                require_current(item)
                require_unlocked(item)
                require_unbound(db, item['uid'])
                if target[0] == wire.GROUP:
                    if origin[0] != wire.GROUP:
                        _require_deposit(item)
                elif target[0] != bag_group(item):
                    raise ValueError('Pet bag withdrawal must use the original item tab')

            from els_server.domain.cartridge_selection_box import BOX
            def stack_state(item):
                return {k: v for k, v in item.items() if k not in ('uid', 'slot', 'count')}

            maximum = TEMPLATE_MAX_STACKS.get(first['template'], 1)
            if second and maximum > 1 and first['template'] != BOX and stack_state(first) == stack_state(second):
                quantity = min(first['count'], maximum - second['count'])
                if quantity > 0:
                    remainder = reduce_count(first, first['count'] - quantity) if quantity < first['count'] else None
                    moved = validate_item(read_stored(dict(second, count=second['count'] + quantity)))
                else:
                    remainder, moved = first, second
            else:
                remainder, moved = second, first

            changes = []
            placements = [(source, remainder if return_position == source else None), (destination, moved)]
            if return_position != source:
                placements.append((return_position, remainder))
            for point, item in placements:
                group, slot = point
                if item is not None and group != wire.GROUP:
                    item = validate_item(relocate(item, dict(item, group=group, slot=slot)))
                changes.append((point, item))
            answer = wire.moved(changes)
            encode_event(answer)

            db.execute('''CREATE TABLE IF NOT EXISTS pet_bag_items (
                uid INTEGER PRIMARY KEY, owner INTEGER NOT NULL REFERENCES characters(uid),
                pet INTEGER NOT NULL REFERENCES companions(uid),
                slot INTEGER NOT NULL CHECK(slot BETWEEN 0 AND 15), item_json TEXT NOT NULL,
                UNIQUE(owner, pet, slot))''')
            for point, item in ((source, first), (destination, second)):
                group, slot = point
                if group == wire.GROUP:
                    if slot in contents:
                        db.execute('DELETE FROM pet_bag_items WHERE owner=? AND pet=? AND slot=?',
                                   (owner, pet_uid, slot))
                elif item is not None:
                    remove(db, owner, item)

            for (group, slot), item in changes:
                if item is None:
                    continue
                if group == wire.GROUP:
                    db.execute('INSERT INTO pet_bag_items VALUES (?, ?, ?, ?, ?)',
                               (item['uid'], owner, pet_uid, slot, json.dumps(legacy(item), sort_keys=True)))
                else:
                    insert(db, owner, item)
                    if load_items(db, owner, item_uid=item['uid']) != [item]:
                        raise ValueError('Pet bag withdrawal did not preserve the item state')
            # Only character inventory positions are usable by ordinary item
            # previews. A deposit must invalidate a preview of the old UID.
            _commit(db, operation, digest, owner, 0x104, [point for point, _ in changes],
                    [item for point, item in ((source, first), (destination, second))
                     if point[0] != wire.GROUP and item is not None],
                    [item for point, item in changes if point[0] != wire.GROUP and item is not None])
            guard(db)
            return answer
