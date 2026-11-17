"""Register 980047 晋级时装（15日）宝箱 as the fifteen-day sibling of 135666.

The item is an owned box that the running tree never consumed: it is absent
from every reference archive branch and from catalog(), so 0x196 answered
with code -1 and the client showed nothing.

135666 晋级时装（7日）宝箱 already carries the approved per-class promotion
fashion mapping for all 194 classes, each entry with inventory_days 7. The
client names 980047 as the same product with a fifteen-day duration, and the
client catalog exposes no separate item-group table for it (rules and
ItemManager both stop at symbolic calls), so the fifteen-day box reuses the
approved mapping and changes only the duration. Nothing else is invented: the
outputs, quantities, metadata, bag group and stack cap are the ones already
running for 135666.

Both the data identity (DATA_SHA) and the module's BOXES set have to move
together, because catalog() rejects a table whose scope differs from BOXES.
"""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'els_server/data/owned_reward_boxes.json'
MODULE = ROOT / 'els_server/domain/owned_reward_boxes.py'
BASE = 135666
TARGET = 980047
DAYS = 15
NOTE = ('Fifteen-day sibling of 135666 晋级时装（7日）宝箱. The per-class promotion '
        'fashion mapping is the already approved one; only the client-stated duration '
        'differs. 980047 carries no decodable item-group table of its own.')


def main():
    import sys
    sys.path.insert(0, str(ROOT))
    from els_server.game_data import client_data

    raw = DATA.read_bytes()
    current = hashlib.sha256(raw).hexdigest()
    module = MODULE.read_text(encoding='utf8')
    declared = re.search(r"DATA_SHA='([0-9a-f]{64})'", module)
    if declared is None:
        raise SystemExit('module DATA_SHA not found')
    if declared.group(1) != current:
        raise SystemExit('table already differs from the module identity; refusing to edit')

    doc = json.loads(raw)
    if json.dumps(doc, ensure_ascii=False, indent=2).encode('utf8') + b'\n' != raw:
        raise SystemExit('serialisation is not byte faithful; refusing to edit')

    boxes = doc['boxes']
    if any(row['template'] == TARGET for row in boxes):
        raise SystemExit('980047 is already registered')
    parent = next((row for row in boxes if row['template'] == BASE), None)
    if parent is None:
        raise SystemExit('135666 is missing; cannot derive the fifteen-day box')

    item = client_data().item(TARGET)
    record_sha = hashlib.sha256(item['record']).hexdigest()
    outputs = {}
    for key, entries in parent['class_outputs'].items():
        outputs[key] = [dict(entry, inventory_days=DAYS) for entry in entries]

    row = {
        'template': TARGET,
        'name': item['name'],
        'metadata': item['metadata'],
        'group': parent['group'],
        'max_stack': parent['max_stack'],
        'record_sha256': record_sha,
        'selection_count': parent['selection_count'],
        'class_outputs': outputs,
        'original_random_rule': dict(parent['original_random_rule'],
                                     m_ItemID=TARGET),
        'source': NOTE,
    }
    if 'original_random_rule' in parent and isinstance(parent['original_random_rule'], dict):
        # The per-class item-group ids belong to the parent item; keep them as a
        # provenance pointer only, and never let them claim 980047's own scope.
        row['original_random_rule']['m_ItemID'] = TARGET

    index = boxes.index(parent) + 1
    boxes.insert(index, row)

    payload = (json.dumps(doc, ensure_ascii=False, indent=2) + '\n').encode('utf8')
    DATA.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()

    module = module.replace(declared.group(1), digest)
    box_line = re.search(r'^BOXES=frozenset\(\((.*?)\)\)$', module, re.M)
    if box_line is None:
        raise SystemExit('BOXES declaration not found')
    members = [int(part) for part in box_line.group(1).split(',') if part.strip()]
    if TARGET not in members:
        members.append(TARGET)
        replacement = 'BOXES=frozenset((%s))' % ','.join(str(m) for m in members)
        module = module[:box_line.start()] + replacement + module[box_line.end():]
    # Write bytes: text mode would translate every LF to CRLF on Windows and
    # turn this one-line change into a whole-file diff.
    MODULE.write_bytes(module.encode('utf8'))

    print('boxes %d -> %d' % (len(boxes) - 1, len(boxes)))
    print('classes %d' % len(outputs))
    print('size %d -> %d' % (len(raw), len(payload)))
    print('record_sha256 %s' % record_sha)
    print('DATA_SHA %s -> %s' % (declared.group(1), digest))


if __name__ == '__main__':
    main()
