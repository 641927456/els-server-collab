"""Register two native story quests that the client offers but the server refuses.

47000 (Lv99, kill 5x NPC 6501 in 34090 -> 130208 x5) and 42650 (Elsword story,
clear 5 dungeons -> 188598 x1) exist in the pinned FieldQuest/FieldSubQuest dump
but were never copied into els_server/data/seal_quests.json, so the accept path
answered 2005 (QUEST_REWARD_UNAVAILABLE) and the client showed nothing.

The file is CRLF JSON with 2-space indent; the rest of the bytes must not move.
"""
import hashlib, json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'els_server/data/seal_quests.json'
MANIFEST = ROOT / 'els_server/data/seal_quests.manifest.json'
DUMP_Q = ROOT / 'analysis/seal-quests-20261015/FieldQuest.tables.json'
DUMP_S = ROOT / 'analysis/seal-quests-20261015/FieldSubQuest.tables.json'
WANT_Q = (47000, 42650)
WANT_S = (47000, 41990)


def dump_records(path):
    calls = json.loads(path.read_text(encoding='utf8'))['__symbolic_calls__']
    rows = {}
    for call in calls:
        for arg in call.get('arguments') or ():
            if isinstance(arg, dict) and 'm_iID' in arg:
                rows[int(arg['m_iID'])] = arg
    return rows


def dumps(payload):
    return (json.dumps(payload, ensure_ascii=False, indent=2) + '\n').replace('\n', '\r\n').encode('utf8')


raw = DATA.read_bytes()
row = json.loads(raw)
manifest = json.loads(MANIFEST.read_bytes())
if hashlib.sha256(raw).hexdigest() != manifest['sha256']:
    raise SystemExit('manifest already out of sync, refusing to edit')
if dumps(row) != raw:
    raise SystemExit('serialisation is not byte faithful, refusing to edit')

for name, want in (('quests', WANT_Q), ('subquests', WANT_S)):
    if any(str(i) in row[name] for i in want):
        raise SystemExit(name + ' already holds ' + str(want))

quests, subs = dump_records(DUMP_Q), dump_records(DUMP_S)
for identity in WANT_Q:
    row['quests'][str(identity)] = quests[identity]
for identity in WANT_S:
    row['subquests'][str(identity)] = subs[identity]


def insert_by_neighbour(name, identity):
    """Place a key after its numeric predecessor without reordering anything.

    subquests already carry seven historical out-of-order appends, so a plain
    re-sort would rewrite the whole section. Inserting next to the neighbour
    keeps every existing byte in place.
    """
    current = row[name]
    ordered = list(current.items())
    target = int(identity)
    at = 0
    for index, (key, _) in enumerate(ordered):
        if int(key) < target:
            at = index + 1
    ordered.insert(at, (str(identity), current.pop(str(identity))))
    row[name] = dict(ordered)


for name, want in (('quests', WANT_Q), ('subquests', WANT_S)):
    for identity in want:
        insert_by_neighbour(name, identity)

body = dumps(row)
shutil.copy2(DATA, DATA.with_suffix('.json.bak-20261105-1940'))
DATA.write_bytes(body)
manifest['sha256'] = hashlib.sha256(body).hexdigest()
MANIFEST.write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').replace('\n', '\r\n').encode('utf8'))
print('quests', len(row['quests']), 'subquests', len(row['subquests']))
print('size', len(raw), '->', len(body))
print('sha256', manifest['sha256'])
