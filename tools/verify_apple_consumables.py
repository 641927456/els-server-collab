"""New apple box -> shortcut -> use compositions in private API-created saves."""
from contextlib import closing
import concurrent.futures
import json
from pathlib import Path
import sqlite3
import struct
import sys
import time
import traceback
from unittest.mock import patch

O = Path(__file__).resolve().parents[1]
V = O
sys.path.insert(0, str(V))
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items, load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES, TEMPLATE_BAG_GROUPS
from els_server.storage.fixed_cubes import open_cube
from els_server.storage.quick_slots import save_request
from els_server.storage.consumables import use as _use
from functools import partial
use = partial(_use, allow_apples=True)
from els_server.domain.consumables import require_usable
from els_server.domain.quick_bindings import item_binding
from els_server.domain.cubes import catalog

import tempfile, atexit
private = tempfile.TemporaryDirectory(prefix='els-apple-qa-')
atexit.register(private.cleanup)
F = Path(private.name)
path = F / 'game.sqlite3'
account = LocalAccount(LocalState(path))
account.enable_characters()
a = account.characters.create('AppleOne', 1, 'own-apple-a')['uid']
b = account.characters.create('AppleTwo', 15, 'own-apple-b')['uid']
for uid in (a, b):
    account.for_character(uid).get_inventory_snapshot()
with closing(sqlite3.connect(path)) as db, db:
    db.execute('UPDATE characters SET level=99 WHERE uid IN (?,?)', (a, b))

def inventory(uid=a):
    with closing(sqlite3.connect(path)) as db:
        return load_items(db, uid)

def seed(t, n=1, uid=a):
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        return grant_items(db, [dict(template=t, metadata=VERIFIED_TEMPLATES[t],
            group=TEMPLATE_BAG_GROUPS[t], quantity=n)], uid)[0]

def box_request(uid, choice):
    return struct.pack('>QBBBIii', uid, 0, 0, 0, 1, choice, 0)

def bind(template, uid=a):
    values = [item_binding(template)] + [0] * 5
    return save_request(path, struct.pack('>iI', 1, 6) + b''.join(
        struct.pack('>ii', slot, value) for slot, value in enumerate(values)), uid)

def snapshot():
    with closing(sqlite3.connect(path)) as db:
        return {n: db.execute('SELECT * FROM "' + n + '" ORDER BY rowid').fetchall()
                for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}

def total(t, uid=a):
    return sum(i['count'] for i in inventory(uid) if i['template'] == t)

def rejected(fn):
    before = snapshot()
    try:
        fn()
    except (ValueError, sqlite3.IntegrityError):
        assert snapshot() == before
    else:
        raise AssertionError('Expected atomic rejection')

checks = []
try:
    assert 723603 not in catalog() and 723604 not in catalog()
    other = inventory(b)
    for index, template in enumerate((710313, 710314, 710315)):
        box = seed(723602)
        wire = box_request(box['uid'], template)
        opened = open_cube(path, a, 723602, wire, 'new-apple-box-' + str(template))
        assert [e.kind for e in opened] == [0xad8, 0x197]
        assert total(template) == 50
        before = snapshot()
        open_cube(path, a, 723602, wire, 'new-apple-box-' + str(template))
        assert snapshot() == before
        bind(template)
        now = 2000000000 + 60 * index
        payload = bytes(5)
        result = use(path, a, payload, 'new-apple-use-' + str(template), now=now)
        assert [e.kind for e in result] == [0x114, 0x115]
        assert result[1].payload == struct.pack('>Qi?Q?', a, template, False, 0, False)
        assert total(template) == 49
        before = snapshot()
        retry = use(path, a, payload, 'new-apple-use-' + str(template), now=now+1)
        assert [e.kind for e in retry] == [0x114] and snapshot() == before
        rejected(lambda: use(path, a, payload, 'cooldown-' + str(template), now=now+29))
        cold = LocalAccount(LocalState(path, a))
        cold.enable_characters()
        assert sum(i['count'] for i in cold.get_inventory_snapshot()['items']
                   if i['template'] == template) == 49
        checks.append('exact-box-choice-manual-use-retry-cold-read-' + str(template))
    assert inventory(b) == other
    for template, level in ((710313, 39), (710314, 49), (710315, 49)):
        try:
            require_usable(template, level)
        except ValueError:
            pass
        else:
            raise AssertionError('Minimum level bypass')
        require_usable(template, level+1)
    checks.append('minimum-level-source-boundaries')
    bind(710314)
    rejected(lambda: use(path, b, bytes(5), 'foreign-empty-shortcut', now=2000000500))
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('UPDATE characters SET level=49 WHERE uid=?', (a,))
    rejected(lambda: use(path, a, bytes(5), 'underlevel', now=2000000500))
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('UPDATE characters SET level=99 WHERE uid=?', (a,))
    item = next(i for i in inventory() if i['template'] == 710314)
    from els_server.storage.item_locks import assign
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('BEGIN IMMEDIATE')
        assign(db, a, item['uid'], int(time.time()) + 86400)
    rejected(lambda: use(path, a, bytes(5), 'locked', now=2000000500))
    checks.append('foreign-underlevel-locked-atomic-rejections')
    # A late encoding failure and a late SQL failure must refund both count
    # and cooldown. Do not resend a possibly committed request blindly.
    bind(710315)
    with patch('els_server.storage.consumables.effect', side_effect=ValueError('apple-encoder-fault')):
        rejected(lambda: use(path, a, bytes(5), 'encoder-fault', now=2000000500))
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("CREATE TRIGGER apple_receipt_fault BEFORE INSERT ON consumable_uses WHEN NEW.operation_id='sql-fault' BEGIN SELECT RAISE(ABORT,'apple-receipt-fault'); END")
    rejected(lambda: use(path, a, bytes(5), 'sql-fault', now=2000000500))
    checks.append('encoder-and-receipt-fault-count-cooldown-rollback')
    old_count = total(710315)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        answers = list(pool.map(lambda _: use(path, a, bytes(5), 'same-apple-race', now=2000000500), range(4)))
    assert total(710315) == old_count-1
    assert sum(e.kind == 0x115 for answer in answers for e in answer) == 1
    checks.append('concurrent-retry-one-debit-one-native-effect')
    # Apples share the original cooldown group10 despite different bindings.
    bind(710313)
    rejected(lambda: use(path, a, bytes(5), 'cross-apple-cooldown', now=2000000529))
    use(path, a, bytes(5), 'cross-apple-ready', now=2000000530)
    checks.append('different-apples-share-exact30second-cooldown')
    # One remaining apple removes the complete instance and survives cold read.
    seed(710314, 1, b)
    bind(710314, b)
    use(path, b, bytes(5), 'last-apple', now=2000000500)
    assert total(710314, b) == 0
    checks.append('last-owned-unit-removed')
    result = dict(ok=True, checks=checks, actual_client=False, temporary_API_created_saves=True,
                  client_effect_math_or_timers_added=False, SDK=False)
    print(json.dumps(result))
except BaseException:
    print(json.dumps(dict(completed=checks,error=traceback.format_exc()),indent=2))
    raise
