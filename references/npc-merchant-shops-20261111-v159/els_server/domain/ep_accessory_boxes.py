"""Ariel's three Camilla accessory cubes from the CN 2025-03-12 update."""
from functools import lru_cache
import hashlib
import json
import struct

from els_server.game_data import client_data

# Prices explicitly confirmed for this server on 2026-11-11. Contents match
# the original KIM descriptions and RandomItem selection counts.
BOXES = {
    719993: (10, (720000, 720001, 720002, 720003)),
    719994: (5, (720009,)),
    719995: (5, (720012,)),
}
REWARDS = frozenset(t for _, outputs in BOXES.values() for t in outputs)


@lru_cache(maxsize=1)
def catalog():
    data = client_data()
    with data.read_session():
        readers = {template: dict(_reader(data.item(template), 3, 2), previously_registered=True)
                   for template in sorted(REWARDS)}
        boxes = {}
        for template, (_, outputs) in BOXES.items():
            boxes[template] = dict(
                _reader(data.item(template), 7, 4),
                selection_count=int(len(outputs) > 1),
                class_outputs={'0': [dict(template=t, quantity=1, inventory_days=7)
                                     for t in outputs]},
            )
    return boxes, readers


def _reader(item, item_type, group):
    if ((item['item_type'], item['metadata']) != (item_type, 0)
            or struct.unpack_from('<I', item['record'], 0x10)[0] != 0
            or not item['name'].startswith('[阿莉尔]卡密拉的')):
        raise ValueError('Camilla EP box native item definition')
    return dict(template=item['id'], name=item['name'], metadata=0, group=group, max_stack=1,
                record_sha256=hashlib.sha256(item['record']).hexdigest())


@lru_cache(maxsize=3)
def definition_sha(template):
    boxes, readers = catalog()
    reward_readers = [readers[t] for t in BOXES[template][1]]
    return hashlib.sha256(json.dumps([boxes[template], reward_readers], sort_keys=True).encode()).hexdigest()
