"""Trace a current-parent career use and same-slot equip in an owned client."""

from contextlib import closing
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import uuid

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
RUNTIME = Path(json.loads((ROOT / 'analysis/publisher-v195-20261113-v1/publication/actual-components.json').read_bytes())['root'])
sys.path[:0] = [str(RUNTIME), str(RUNTIME / 'tools'), str(RUNTIME / 'vendor'), str(ROOT / 'tools/pylibs')]
spec = importlib.util.spec_from_file_location('owned_harness', ROOT / 'analysis/shop-open-20261110-v1/verify.py')
harness = importlib.util.module_from_spec(spec)
module_search_path = sys.path[:]
spec.loader.exec_module(harness)
sys.path[:] = module_search_path
harness.RUNTIME = RUNTIME


def seed(path, uid, account):
    from els_server.game_data import client_data
    from els_server.storage.inventory_state import grant_items
    from els_server.storage.local_state import LocalState

    assert path.parent.parent == WORK and path.parent.name.startswith('owned-native-') and uid == 1001
    template = 318854
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('UPDATE characters SET unit_class=66,transcendence=1 WHERE uid=?', (uid,))
        ticket = grant_items(db, [dict(template=template, metadata=client_data().item(template)['metadata'],
                                       group=4, quantity=1)], uid)[0]
    LocalState(path, uid).save_skills((21100, 21101, 21102, 21246, 21026) + (0,) * 17, account_id=account)
    (path.parent / 'fixture.json').write_text(json.dumps(dict(uid=ticket['uid'], template=template)), 'utf8')


def trigger(home, session, event, sequence, result):
    from els_server.protocol.protocol_codec import Event
    from els_server.storage.career_shop import notifications
    from els_server.storage.careers import use_career_item
    from els_server.storage.seal_quests import load_character

    if (event.event_id != 0x202 or event.kind != 0x225 or not result
            or session.account is None or session.account.uid != 1001
            or session.account.character()['unit_class'] != 66):
        return []
    assert session.account.store.path.parent == home
    location = session.account.get_location()

    def prepare(db, receipt):
        before, after = receipt['before'], receipt['after']
        current = load_character(db, 1001, session.account.account_id)
        return [Event(0x201, kind=0x21a, payload=receipt['response'])] + notifications(
            db, 1001, dict(current, **before), location, before, after, False)

    item = json.loads((home / 'fixture.json').read_bytes())
    payload = struct.pack('>QQiiIB', item['uid'], 0, 0, 0, 0, 0)
    answer = use_career_item(session.account.store.path, 1001, payload,
                             f'owned-client-entry-{sequence}', prepare_refresh=prepare)['prepared_events']
    assert any(e.kind == 0x29f for e in answer)
    print('OWNED_ENTRY_CAREER', [hex(e.kind) for e in answer], flush=True)
    return answer


def serve(home):
    from els_server.domain.tutorial_quests import restore_initialization

    assert Path(inspect.getfile(restore_initialization)).is_relative_to(RUNTIME)
    assert 'refresh_active' in inspect.signature(restore_initialization).parameters
    if '--candidate' in sys.argv:
        import els_server.domain
        import els_server.protocol
        import els_server.storage

        for package in (els_server.domain, els_server.protocol, els_server.storage):
            package.__path__.insert(0, str(WORK / 'candidate' / Path(*package.__name__.split('.'))))
    source = inspect.getsource(harness.serve)
    marker = '    ctx = dict(__name__='
    assert source.count(marker) == 1
    source = source.replace('    load_fix()\n', '')
    source = source.replace(marker, "    code = code.replace('        register(config.state_file', '        seed(config.state_file,uid,aid)\\n        register(config.state_file')\n"
                            "    code = code.replace('event.kind in (0x51c,', 'event.kind in (0x219, 0x122, 0x51c,')\n"
                            "    code = code.replace('0x227, 0x80d,', '0x227, 0x28, 0x6e9, 0x5bf, 0x32, 0x80d,')\n"
                            "    if trigger_at_entry:\n"
                            "        code = code.replace('            return result\\n', '            return result + trigger(home, session, event, sequence, result)\\n')\n"
                            "    ctx = dict(seed=seed, trigger=trigger, __name__=")
    namespace = dict(vars(harness), seed=seed, trigger=trigger, trigger_at_entry='--at-entry' in sys.argv)
    exec(compile(source, str(__file__), 'exec'), namespace)
    namespace['serve'](home)


def rows(path):
    if not path or not path.is_file():
        return []
    return [json.loads(line) for line in path.read_bytes().splitlines(keepends=True) if line.endswith(b'\n')]


def launch_job(home, *, prior_support=False):
    ready = json.loads((home / 'ready.json').read_bytes())
    assert ready['uid'] == 1001 and home.parent == WORK
    source_path = ROOT / 'analysis/protocol-readwrite-20261112-v1/native-validation-20261113/runner-plan/native_runner.py'
    client = Path('D:/艾尔之光/艾尔之光-朋友服/data/x2_dx11.exe') if prior_support else Path('D:/艾尔之光/data/x2_dx11.exe')
    runtime = (ROOT / 'analysis/publisher-continuation-20261111-v1/release-v187-consolidated/qa-target-161f1f4cde29f2be'
               if prior_support else RUNTIME)
    probe = runtime / 'tools/probe_updated_client.py'
    run = home / 'runs'
    run.mkdir()
    (home / 'observer.js').rename(run / 'observer.js')
    config = dict(runtime=str(runtime), client=str(client), local_port=ready['bridge_port'],
                  client_sha='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709',
                  probe_sha=hashlib.sha256(probe.read_bytes()).hexdigest(), native_seconds=130)
    (run / 'probe-input.json').write_text(json.dumps(config), 'utf8')
    source = source_path.read_text('utf8')
    for old, new in (
        ('assert port==19434', "assert port==19432 and cfg['local_port']==port"),
        ("'--no-auto-entry','--until-stopped','--local-resource-index','--item-test','--npc-slot-test',",
         "'--no-auto-entry','--until-stopped','--local-resource-index','--lightweight-play','--item-test','--npc-slot-test',"),
    ):
        assert source.count(old) == 1
        source = source.replace(old, new)
    source = '\n'.join(line for line in source.splitlines() if 'publish_owned_pvp_support' not in line) + '\n'
    sys.argv = [str(source_path), str(run)]
    exec(compile(source, str(source_path), 'exec'), dict(__name__='__main__', __file__=str(source_path)))


def native():
    from client_process_guard import has_running_client

    lock = ROOT / 'analysis/coordination-20261015/isolated-game-test.lock'
    deadline = time.monotonic() + (240 if '--wait-for-slot' in sys.argv else 0)
    while lock.exists() or has_running_client():
        if time.monotonic() >= deadline:
            raise RuntimeError('Original client or its isolated slot is already in use')
        time.sleep(.5)
    with TemporaryDirectory(dir=WORK, prefix='owned-native-') as directory:
        home = Path(directory)
        identity = dict(pid=os.getpid(), directory=str(home), token=uuid.uuid4().hex,
                        owner=WORK.name, purpose='Third-job ordinary shortcut refresh')
        own_lock = False
        host = client = None
        candidate = '--candidate' in sys.argv
        at_entry = '--at-entry' in sys.argv
        job = '--job' in sys.argv
        prior_support = '--prior-support' in sys.argv
        report = dict(ok=False, source='V195 signed components', candidate=candidate, at_entry=at_entry,
                      job=job, support='V187 qualified QA' if prior_support else 'V195 signed',
                      natural_input=False, player_data=False)
        command = [sys.executable, '-u', '-B', '-X', 'utf8', str(Path(__file__).resolve())]

        def trace():
            return [x.get('payload', {}) for x in rows(next((home / 'runs').glob('**/trace.jsonl'), None))]

        def event(name):
            return next((x for x in trace() if x.get('event') == 'third_job_' + name), None)

        def wait(process, predicate, seconds):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f'Owned process exited {process.returncode}')
                failure = event('error') or event('timeout') or next((x for x in trace() if x.get('event') == 'owned_qa_entry_error'), None)
                if failure:
                    raise RuntimeError(failure)
                value = predicate()
                if value:
                    return value
                time.sleep(.25)
            raise TimeoutError('Owned client phase deadline')

        try:
            with lock.open('x', encoding='utf8') as handle:
                json.dump(identity, handle)
                own_lock = True
            assert not has_running_client()
            with (home / 'server.log').open('wb') as server_log, (home / 'client.log').open('wb') as client_log:
                options = [opt for opt in ('--candidate', '--at-entry') if opt in sys.argv]
                host = subprocess.Popen([*command, 'serve', str(home), *options], cwd=ROOT, stdout=server_log,
                                        stderr=server_log, creationflags=subprocess.CREATE_NO_WINDOW)
                wait(host, lambda: (home / 'ready.json').is_file(), 85)
                town = (ROOT / 'analysis/daily-weekly-seasonpass-20261109-v1/enter_owned_town.js').read_text('utf8')
                if job:
                    # The newer owned worker selects as soon as the channel list arrives.
                    assert town.count('Date.now()-selected>5000&&') == 1
                    town = town.replace('Date.now()-selected>5000&&', '')
                probe = (WORK / 'observe.js').read_text('utf8')
                fixture = json.loads((home / 'fixture.json').read_bytes())
                fixture['candidate'] = candidate
                fixture['atEntry'] = at_entry
                (home / 'observer.js').write_text(town + '\n' + probe.replace('__FIXTURE__', json.dumps(fixture)), 'utf8')
                launch_options = ['--prior-support'] if prior_support else []
                client = subprocess.Popen([*command, 'launch-job' if job else 'launch', str(home), *launch_options], cwd=ROOT, stdout=client_log,
                                          stderr=client_log, creationflags=subprocess.CREATE_NO_WINDOW)
                phases = [('before', 105), ('after', 30)]
                if not candidate:
                    phases.append(('after_equip', 15))
                for name, limit in phases:
                    report[name] = wait(client, lambda: event(name), limit)
                    print(name, json.dumps(report[name]), flush=True)
                old_skills = [21100, 21101, 21102, 21246, 21026]
                new_skills = [21113, 21114, 21115, 21251, 21026]
                assert report['after']['sameUnit'] and report['after']['cls'] == 79
                assert [x['skill'] for x in report['after']['slots']] == (new_skills if candidate else old_skills)
                if not candidate:
                    assert report['after_equip']['sameUnit']
                    assert [x['skill'] for x in report['after_equip']['slots']] == [21113, *old_skills[1:]]
                report['ok'] = True
        finally:
            try:
                if client is not None:
                    for path in (home / 'runs').glob('**/client-process.json'):
                        (path.parent / 'client.stop').write_text('Owned career observation ended', 'utf8')
                    try:
                        client.wait(20)
                    except subprocess.TimeoutExpired:
                        client.terminate()
                        client.wait(10)
            finally:
                try:
                    if host is not None:
                        (home / 'stop').write_text('Owned career observation ended', 'utf8')
                        host.wait(30)
                finally:
                    if own_lock and json.loads(lock.read_bytes()) == identity:
                        lock.unlink()
                    report['trace'] = [x for x in trace() if x.get('event', '').startswith(('third_job_', 'owned_qa_'))]
                    report['isolation'] = (json.loads((home / 'runs/closed.json').read_bytes())
                                           if (home / 'runs/closed.json').is_file() else None)
                    if (home / 'game.sqlite3').is_file():
                        with closing(sqlite3.connect((home / 'game.sqlite3').as_uri() + '?mode=ro', uri=True)) as db:
                            row = db.execute('SELECT payload,revision FROM skill_slots WHERE uid=1001').fetchone()
                        report['cold_slots'] = list(struct.unpack('>22i', row[0])) if row else None
                        report['cold_revision'] = row[1] if row else None
                    if not report['ok']:
                        report['last_events'] = [x.get('event') for x in trace()[-25:]]
                        report['startup_diagnostics'] = [
                            {key: x.get(key) for key in ('event', 'event_kind', 'status', 'reason', 'operation', 'code', 'trigger', 'api') if key in x}
                            for x in trace() if x.get('event') in ('process_exit_requested', 'run_error_context', 'client_event_send')
                        ][-25:]
                        all_events = trace()
                        base = next((int(x['base'], 16) for x in all_events if x.get('event') == 'module_loaded'
                                     and x.get('name', '').lower() == 'x2_dx11.exe'), None)
                        report['client_faults'] = [
                            dict(code=x['code'], game_rva=hex(int(x['address'], 16) - base) if base else None)
                            for x in all_events if x.get('event') == 'original_fatal_exception'
                        ]
                        report['failure'] = {n: (home / n).read_text('utf8', errors='replace')[-2500:]
                                             for n in ('server.log', 'client.log') if (home / n).exists()}
                    report['test_requests'] = [
                        {key: x[key] for key in ('kind', 'phase', 'replies')}
                        for x in rows(home / 'events-private.jsonl') if x.get('event') == 'owned_camilla_protocol'
                    ]
                    with (WORK / 'client-observations.jsonl').open('a', encoding='utf8') as handle:
                        handle.write(json.dumps(report) + '\n')


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'native':
        native()
    elif action == 'serve':
        serve(Path(sys.argv[2]))
    elif action == 'launch':
        harness.launch(Path(sys.argv[2]))
    elif action == 'launch-job':
        launch_job(Path(sys.argv[2]), prior_support='--prior-support' in sys.argv)
