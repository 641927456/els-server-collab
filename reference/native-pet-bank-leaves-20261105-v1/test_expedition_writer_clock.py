"""Three original region1 transitions behind a real independent SQLite writer."""
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch
from datetime import datetime, timezone
import hashlib, json, os, sqlite3, struct, sys, tempfile, time, traceback, uuid

W = Path(__file__).resolve().parent
BASE = Path(os.environ['ELS_FULL_SOURCE']).resolve()
baseline = '--baseline' in sys.argv
sys.dont_write_bytecode = True
sys.path[:0] = [str(BASE), str(BASE / 'vendor'), 'G:/els/tools/pylibs']
import ctypes
_sqlite_runtime = ctypes.WinDLL(str(BASE / 'python/sqlite3.dll'))
import els_server, els_server.storage, els_server.domain, els_server.protocol
source = W / ('baseline' if baseline else 'source') / 'els_server'
els_server.storage.__path__.insert(0, str(source / 'storage'))
els_server.domain.__path__.insert(0, str(source / 'domain'))
from els_server.storage import pet_expedition as state
from els_server.storage.characters import Characters
from els_server.storage.game_schema import prepare
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.storage.inventory_state import grant_items
from els_server.storage.inventory_state import load_items
from els_server.storage import companion_state, pet_progression, life_stamina
from els_server.domain.pet_progression import template, threshold
from els_server.domain.pet_expedition import source_terms
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.protocol.local_messages import wstring

BOUNDARY = int(datetime(2030, 3, 17, 2, tzinfo=timezone.utc).timestamp())  # CN10:00
report = dict(passed=False, baseline=baseline, cases=[], actual_SQL_writer_competition=True,
              approved_region=1, natural_acquisition=False, production_database_access=False)

def blocked(path, before, after, call):
    clock = [before]
    entered = Event()
    class Waiting(sqlite3.Connection):
        def execute(self, sql, *args, **kwargs):
            if sql == 'BEGIN IMMEDIATE':
                entered.set()
            return super().execute(sql, *args, **kwargs)
    def connect(*args, **kwargs):
        return sqlite3.connect(*args, **kwargs, factory=Waiting)
    with closing(sqlite3.connect(path)) as holder:
        holder.execute('BEGIN IMMEDIATE')
        with ThreadPoolExecutor(max_workers=1) as pool, patch.object(state, 'sqlite3', SimpleNamespace(connect=connect)), \
             patch.object(state, 'time', SimpleNamespace(time=lambda: clock[0])):
            future = pool.submit(call)
            assert entered.wait(3)
            clock[0] = after
            holder.commit()
            try:
                return True, future.result(timeout=5)
            except ValueError as error:
                return False, str(error)

try:
    cases = tuple(sys.argv[sys.argv.index('--case') + 1].split(',')) if '--case' in sys.argv else ('board', 'start', 'complete', 'failed_result', 'reward')
    for case in cases:
        with tempfile.TemporaryDirectory(prefix='owned-expedition-clock-', dir=W) as directory:
            path = Path(directory) / 'own.sqlite3'
            prepare(path)
            roster = Characters(path, 1)
            uid = roster.create('OwnExpClock', 1, 'own-exp-clock-create')['uid']
            account = LocalAccount(LocalState(path, uid), account_id=1)
            account.enable_characters(characters=roster)
            account.get_inventory_snapshot()
            def guard(db):
                assert db.execute('SELECT account_id FROM character_owners WHERE uid=?', (uid,)).fetchone() == (1,)
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('UPDATE characters SET level=99 WHERE uid=?', (uid,))
                db.execute('UPDATE reward_balances SET ed=6000000 WHERE uid=?', (uid,))
                life_stamina.initialize(db, uid, 1, str(uuid.uuid4()), BOUNDARY - 3)
                egg = grant_items(db, [dict(template=500051, metadata=VERIFIED_TEMPLATES[500051],
                    group=TEMPLATE_BAG_GROUPS[500051], quantity=1)], uid)[0]
            companion_state.handle(path, uid, 0x2e8, struct.pack('>Q', egg['uid']) + wstring('OwnExpPet'),
                                   'own-exp-clock-egg', account_id=1)
            with closing(sqlite3.connect(path)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                pet = companion_state.rows(db, uid, 'pet')[0]
                pet['step'] = template(pet['unit'])['EVOLUTION_ALL_STEP']
                pet['growth'] = threshold(pet)
                if case == 'reward':
                    pet['personality'] = {str(key): 1000 for key in range(4)}
                pet_progression.save(db, uid, pet)
            state.initialize(path, uid, 1, guard, now=BOUNDARY - 3, randbelow=lambda n: 0)
            payload = struct.pack('>iiIQ', 1, 1, 1, pet['uid'])
            if case == 'board':
                accepted, result = blocked(path, BOUNDARY - 2, BOUNDARY + 1,
                    lambda: state.initialize(path, uid, 1, guard, randbelow=lambda n: 2))
                assert accepted
                with closing(sqlite3.connect(path)) as db:
                    row = db.execute('SELECT mission,refresh_day,generation FROM pet_expedition_runs WHERE owner=?', (uid,)).fetchone()
                expected = (1, life_stamina.day(BOUNDARY - 2), 1) if baseline else (3, life_stamina.day(BOUNDARY + 1), 2)
                assert row == expected
                report['cases'].append(dict(action='idle board crosses approved CN10:00 reset', saved=row))
            else:
                if case == 'start':
                    accepted, result = blocked(path, BOUNDARY - 2, BOUNDARY - 1,
                        lambda: state.perform(path, uid, 1, 0x8c1, payload, 'own-exp-clock-start', guard, randbelow=lambda n: 0))
                else:
                    state.perform(path, uid, 1, 0x8c1, payload, 'own-exp-clock-start', guard,
                                  now=BOUNDARY - 2, randbelow=lambda n: 0)
                    with closing(sqlite3.connect(path)) as db:
                        end = db.execute('SELECT ends_at FROM pet_expedition_runs WHERE owner=?', (uid,)).fetchone()[0]
                    if case == 'reward':
                        assert source_terms(1, [pet])['native_display_percent'] >= 100
                    with closing(sqlite3.connect(path)) as db:
                        items_before = load_items(db, uid)
                    accepted, result = blocked(path, end if case in ('failed_result','reward') else end - 1, end,
                        lambda: state.perform(path, uid, 1, 0x8c3, struct.pack('>ii', 1, 1), 'own-exp-clock-complete', guard, randbelow=lambda n: 0))
                if case == 'start':
                    assert accepted
                    with closing(sqlite3.connect(path)) as db:
                        saved = db.execute('SELECT started_at,ends_at FROM pet_expedition_runs WHERE owner=?', (uid,)).fetchone()
                    terms = source_terms(1, [pet])
                    duration = state._discount(terms['original_minutes'], terms['time_reduce_rate']) * 60
                    start = BOUNDARY - 2 if baseline else BOUNDARY - 1
                    assert saved == (start, start + duration)
                    report['cases'].append(dict(action='start time follows actual writer admission', saved=saved))
                else:
                    assert accepted is (not baseline or case == 'reward'), (accepted, result)
                    if accepted:
                        with closing(sqlite3.connect(path)) as db:
                            saved = list(db.iterdump())
                            items_after = load_items(db, uid)
                        if case == 'reward':
                            assert sum(item['count'] for item in items_after if item['template'] == 135984) == 1
                        else:
                            assert items_after == items_before
                        state.perform(path, uid, 1, 0x8c3, struct.pack('>ii', 1, 1), 'own-exp-clock-complete', guard,
                                      now=end, randbelow=lambda n: 0)
                        with closing(sqlite3.connect(path)) as db:
                            assert saved == list(db.iterdump())
                    if baseline and case == 'failed_result':
                        assert result == 'Inventory grant plan bound'
                    report['cases'].append(dict(action=case, accepted=accepted,
                                               zero_reward=case != 'reward', duplicate_receipt_no_increment=accepted))
        assert not Path(directory).exists()
    report.update(passed=True, owned_temporary_directories_removed=True)
except BaseException:
    report['error'] = traceback.format_exc()
report['source_sha256'] = hashlib.sha256(Path(state.__file__).read_bytes()).hexdigest()
path = W / ('writer-clock-' + ('baseline-' if baseline else 'fixed-') + str(time.time_ns()) + '.json')
path.write_text(json.dumps(report, indent=2) + '\n', 'utf8')
print(json.dumps(dict(report, evidence=str(path))))
raise SystemExit(not report['passed'])
