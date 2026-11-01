"""Run one owned private-desktop startup with an isolated local server and save."""
from pathlib import Path
import ctypes
import datetime
import hashlib
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import traceback
import uuid

ROOT = Path('G:/els')
HERE = Path(__file__).resolve().parent
PARENT = Path(json.loads((HERE/'launcher-v60/selected-support.json').read_bytes())['Friends'])
ORIGINAL = ROOT/'analysis/startup-ui-hide-20261101-v1'
DESKTOP_SOURCE = ROOT / 'analysis/local-activities-20261017-v82/research/background-desktop-v1'
sys.path[:0] = [str(PARENT / 'tools'), str(PARENT / 'tools'), str(PARENT),
               str(ROOT / 'tools/pylibs'), str(DESKTOP_SOURCE)]
import frida
import psutil
from desktop_api import U, K, check, object_name, input_desktop, spawn, exit_code, close_process
from launch_client import prepare_native_sources
from local_stack_limits import source as stack_source
from local_shortcut_totals import source as shortcut_source

def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')

def games():
    return [p.info for p in psutil.process_iter(['pid', 'name', 'create_time'])
            if (p.info['name'] or '').lower() in ('x2.exe', 'x2_dx11.exe')]

observe_only = '--observe-only' in sys.argv
current_desktop = '--current-desktop' in sys.argv
trial = HERE / 'public-ui-trial-2'
trial.mkdir()
report = {'ok': False, 'started': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'scope': 'Owned public Friends startup via authenticated TLS bridge; copied EXE and isolated writable configuration',
          'formal_components_changed': False, 'original_EXE_KOM_modified': False}
client_dir = HERE / 'public-ui-trial-1/client/data'
original = Path('D:/艾尔之光/data')
snapshot = (ROOT / 'analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
exe_sha = '6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
cache_path = PARENT / 'tools/native_cache_sync.py'
cache_ns = {'__file__': str(PARENT / 'tools/native_cache_sync.py')}
exec(compile(cache_path.read_text(encoding='utf8'), str(cache_path), 'exec'), cache_ns)
job_source = ROOT / 'analysis/git-dual-delivery-20261030-v1/v47-private-controls-source-v2/host/owned_job.py'
assert sha(job_source) == '4baca0c5ec32e66deea72adf665e5bb612ab76dcba73039fe2ec09e97f07bfa2'
spec = importlib.util.spec_from_file_location('startup_live_job', job_source)
job_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job_module)
job = None
desktop = pi = session = server = log = server_log = None
scripts = []
events = []
input_before = input_desktop()
U.GetForegroundWindow.restype = ctypes.c_void_p
foreground_before = U.GetForegroundWindow()
try:
    if '--wait-slot' in sys.argv:
        deadline = time.monotonic() + 180
        last = None
        while games() and time.monotonic() < deadline:
            current = [p['pid'] for p in games()]
            if current != last:
                print(json.dumps({'phase':'waiting-for-existing-game-to-exit','protected_pids':current}),flush=True)
                last = current
            time.sleep(1)
    assert not games(), 'Existing game protected; no test launched'
    assert sha(original / 'x2_dx11.exe') == exe_sha
    # Resource files are referenced, not copied or edited. Writable configuration,
    # the actual game EXE and security support files belong to this test only.
    links = []
    copied = []
    if client_dir.exists():
        view=json.loads((HERE/'public-ui-trial-1/client-view.json').read_bytes())
        copied=view['copied'];links=view['resource_file_links']
        for relative in copied:assert sha(client_dir/relative)==sha(original/relative)
        for relative in links:
            path=client_dir/relative;assert path.is_symlink()and path.resolve()==(original/relative).resolve()
    else:
        for source in original.rglob('*'):
            relative = source.relative_to(original)
            if relative.parts[0] == 'ScreenCapture' or relative.name.lower() == 'x2.exe':
                continue
            destination = client_dir / relative
            if source.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            if relative.parts[0] == 'xigncode' or source.suffix.lower() in (
                    '.exe', '.ini', '.lua', '.bat', '.xml', '.json', '.txt'):
                shutil.copy2(source, destination)
                copied.append(str(relative))
            else:
                destination.symlink_to(source)
                links.append(str(relative))
    save(trial / 'client-view.json', {'root': str(client_dir), 'original': str(original),
        'copied': copied, 'resource_file_links': links})
    client = client_dir / 'x2_dx11.exe'
    assert sha(client) == exe_sha
    prepared = prepare_native_sources(snapshot, client_dir, False, True)
    prepared['stack_limits'] = stack_source(snapshot)
    prepared['shortcut_totals'] = shortcut_source(snapshot)
    template = (PARENT / 'tools/trace_dx11_login.js').read_text(encoding='utf8')
    code = cache_ns['compose'](snapshot, exe_sha, template)
    rvas = (0x6845e0, 0x682d80, 0x30f6730, 0x30f8e00, 0x2b4eaa0, 0xd9b170,
            0x137ad80, 0x13a0f90, 0x13aeb90, 0x13a11f0, 0x13835c0)
    replacements = {'__VERIFIED_PREFIXES__': json.dumps({r: snapshot[r:r+8].hex() for r in rvas}),
        '__ENTER_TOWN__': 'true', '__ENTER_DUNGEON__': 'false', '__NPC_CANDIDATE__': 'null',
        '__AUTO_RETURN__': 'false', '__GATE_IDENTITY_TEST__': 'false',
        '__POPULATION_TEST__': 'false', '__LIGHTWEIGHT_PLAY__': 'true'}
    for token, value in replacements.items():
        code = code.replace(token, value)
    if observe_only:
        observer = '''
  const seen = new Set();
  function sample() {
    const tables = [0x42e9b90, 0x42ea0c0].map(r => ({rva:r,
      values:[0,8,16,24].map(o => game.base.add(r+o).readPointer().toString())}));
    const key = JSON.stringify(tables);
    if (!seen.has(key)) {seen.add(key);note({event:'startup_ui_vtable_observation',base:game.base.toString(),tables});}
  }
  sample(); const vtTimer=setInterval(sample,100);
  for(const r of [0xb76c20,0xb76c60,0x30f2050,0x30f2090]){
    let once=false;Interceptor.attach(game.base.add(r),{onEnter(a){if(!once){once=true;note({event:'startup_ui_original_render',rva:r,state:a[0].toString(),vtable:a[0].readPointer().toString()});sample();}}});
  }
'''
        code = code.replace('&&elsStartupVisibilityReady()', '')
        code = code.replace('  installElsStartupVisibility();', observer)
    assert '__STARTUP_UI' not in code
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 19400))
        port = reservation.getsockname()[1]
    qa=json.loads((HERE/'qa-credentials.private.json').read_bytes())
    bridge_config=dict(qa['bridge'],local_port=port)
    config=trial/'bridge.private.json';save(config,bridge_config)
    stop=trial/'server.stop';server_log=(trial/'server-console.txt').open('w',encoding='utf8')
    env=dict(os.environ,PYTHONPATH=str(PARENT),PYTHONDONTWRITEBYTECODE='1')
    job=job_module.OwnedJob()
    server=subprocess.Popen([sys.executable,'-B','-m','els_server.friends_bridge','--config',str(config),'--stop-file',str(stop),'--owner-pid',str(os.getpid()),'--owner-created',repr(psutil.Process().create_time())],cwd=trial,env=env,stdout=server_log,stderr=subprocess.STDOUT,creationflags=0x08000000|4)
    job.assign_suspended(server);job.resume(server)
    end=time.monotonic()+30
    while time.monotonic()<end and server.poll()is None:
        server_log.flush()
        if 'ELS_BRIDGE_READY'in(trial/'server-console.txt').read_text('utf8'):break
        time.sleep(.1)
    else:raise RuntimeError('Owned public TLS bridge readiness failed')
    report['public_TLS']=True;report['account_id']=qa['account_id'];report['selected_support_root']=str(PARENT)
    assert not games(), 'Existing game appeared before owned launch'
    name = input_before if current_desktop else 'ELS_StartupUI_' + uuid.uuid4().hex
    desktop = check(U.OpenDesktopW(name,0,False,0xff) if current_desktop else
        U.CreateDesktopW(name, None, None, 0, 0xff, None))
    report['scope'] = ('Owned nonactivating window; authenticated public TLS bridge, copied executable '
        'and isolated writable client config; no input/focus actions' if current_desktop else report['scope'])
    guard = (DESKTOP_SOURCE / 'client-observer.template.js').read_text(encoding='utf8')
    guard = guard.replace('__PREFIXES__', '{}').replace('__SINK_PORT__', str(port)).replace(
        '__PRIVATE_DESKTOP__', json.dumps(name))
    if not observe_only:
        # Keep native security/browser children in the inherited owned desktop
        # and Job. The earlier no-login observer intentionally denied children.
        begin = guard.index("for(const name of ['CreateProcessW','CreateProcessA']){")
        finish = guard.index('const shellSeen=', begin)
        guard = guard[:begin] + guard[finish:]
        if current_desktop:
            focus_guard = '''
for (const name of ['SetForegroundWindow','BringWindowToTop'])deny(u,name,'int',['pointer'],0);
for (const name of ['SetActiveWindow','SetFocus'])deny(u,name,'pointer',['pointer'],ptr(0));
for (const name of ['CreateWindowExW','CreateWindowExA']){
  const fn=u.findExportByName(name);if(fn)Interceptor.attach(fn,{onEnter(a){a[0]=ptr((a[0].toUInt32()|0x08000000)&~8);}});
}
'''
            guard = guard.replace('const setError=', focus_guard + '\nconst setError=')
        before = "onEnter(a){this.sa=redirect(a,1,2,name);}"
        after = ("onEnter(a){const p=a[1];if(a[2].toInt32()>=16&&p.readU16()===2&&"
            "[9400,19400].includes((p.add(2).readU8()<<8)|p.add(3).readU8()))this.sa=redirect(a,1,2,name);}")
        assert guard.count(before) == 1
        guard = guard.replace(before, after)
        begin = guard.index("for(const [name,at,len] of [['sendto'")
        finish = guard.index('\n', begin)
        guard = guard[:begin] + guard[finish:]
        guard = (ORIGINAL / 'capture_owned_frame.js').read_text(encoding='utf8') + '\n' + guard
        guard = guard.replace('function hookSwap(p){if(p.isNull())return;',
            'function hookSwap(p){if(p.isNull())return;captureSwap(p);')
        guard += '\nrpc.exports.capturestartup=watchStartupFrameStates;\n'
    log = (trial / 'events.private.jsonl').open('w', encoding='utf8', buffering=1)
    def receive(message, data):
        events.append(message)
        log.write(json.dumps(message, ensure_ascii=False) + '\n')
        event = message.get('payload', {})
        if event.get('event') == 'owned_frame_readback':
            from PIL import Image
            label = event['label']
            assert label in ('login','loading','character-selection')
            image = Image.frombytes('RGBA', (event['width'],event['height']), bytes(data),
                'raw','BGRA' if event['format']==87 else 'RGBA',event['pitch'],1).convert('RGB')
            image.save(trial / ('owned-' + label + '.png'))
    pi = spawn([client, 'pxk19slammsu286nfha02kpqnf729ck'], 'WinSta0\\' + name, client_dir, True)
    assert job.k.AssignProcessToJobObject(job.handle, pi.hProcess)
    report['owned_game'] = {'pid': pi.pid, 'created': psutil.Process(pi.pid).create_time(),
        'exe': str(client), 'sha256': sha(client), 'desktop': name}
    save(trial / 'owned-game.json', report['owned_game'])
    session = frida.attach(pi.pid)
    for text in (guard, *prepared.values(), code,
                 (PARENT / 'tools/observe_native_fatal.js').read_text(encoding='utf8')):
        script = session.create_script(text)
        script.on('message', receive)
        script.load()
        scripts.append(script)
    assert not [m for m in events if m.get('type') == 'error']
    assert input_desktop() == input_before
    assert K.ResumeThread(pi.hThread) == 1
    print(json.dumps({'phase': 'owned-game-started', 'pid': pi.pid, 'private_port': port}), flush=True)
    start = time.monotonic()
    announced = set()
    frame_requests = set()
    end_at = None
    selection_seen_at = None
    while exit_code(pi) == 259 and time.monotonic() - start < 100:
        assert input_desktop() == input_before
        payloads = [m.get('payload', {}) for m in events]
        if not observe_only and 'watcher' not in frame_requests and any(
                p.get('event') == 'startup_ui_visibility_ready' for p in payloads):
            scripts[0].exports_sync.capturestartup()
            frame_requests.add('watcher')
        for event in payloads:
            kind = event.get('event', '')
            if kind in ('startup_ui_visibility_ready', 'startup_ui_render_scope_entered',
                        'startup_ui_visibility_finished', 'character_list_payload_parsed',
                        'local_identity_native_request', 'original_fatal_exception',
                        'startup_ui_vtable_observation','startup_ui_original_render'):
                key = kind + ':' + str(event.get('page', event.get('reason', event.get('rva', ''))))
                if key not in announced:
                    print(json.dumps(event, ensure_ascii=False), flush=True)
                    announced.add(key)
            label = ('character-selection' if kind == 'startup_ui_visibility_finished' and
                    event.get('reason') == 'character-selection' else None)
            if label == 'character-selection':
                selection_seen_at = selection_seen_at or time.monotonic()
                if time.monotonic() - selection_seen_at < 10:
                    label = None
            if label and not observe_only and label not in frame_requests:
                scripts[0].post({'type':'capture_owned_frame','payload':{'label':label}})
                frame_requests.add(label)
        done = next((p for p in payloads if p.get('event') == 'startup_ui_visibility_finished'), None)
        if done:
            report['visibility_terminal'] = done
            end_at = end_at or time.monotonic() + 15
        if observe_only and any(p.get('event') == 'updated_character_frame' for p in payloads):
            end_at = end_at or time.monotonic() + 3
        if any(m.get('type') == 'error' for m in events):
            report['agent_error'] = True
            break
        if any(p.get('event') == 'original_fatal_exception' for p in payloads):
            report['native_fatal'] = True
            break
        if end_at and time.monotonic() >= end_at:
            break
        save(trial / 'progress.json', {'elapsed': round(time.monotonic() - start, 2),
            'events': len(events), 'announced': sorted(announced)})
        time.sleep(.2)
    payloads = [m.get('payload', {}) for m in events]
    report['elapsed_seconds'] = round(time.monotonic() - start, 3)
    report['events'] = [p for p in payloads if p.get('event', '').startswith('startup_ui_')]
    report['roster_received'] = any(p.get('event') == 'character_list_payload_parsed' and
        p.get('ok') and p.get('result') == 0 for p in payloads)
    report['agent_errors'] = [m for m in events if m.get('type') == 'error']
    report['frame_readbacks'] = [p for p in payloads if p.get('event','').startswith('owned_frame_readback')]
    report['native_exit_before_cleanup'] = exit_code(pi)
    report['ok'] = (report.get('visibility_terminal', {}).get('reason') == 'character-selection'
        and report['roster_received'] and not report['agent_errors'])
except BaseException:
    report['error'] = traceback.format_exc()
finally:
    if pi:
        if exit_code(pi) == 259:
            check(K.TerminateProcess(pi.hProcess, 95))
            K.WaitForSingleObject(pi.hProcess, 10000)
        report['owned_game_exited'] = exit_code(pi) != 259
        close_process(pi)
    if session:
        try:
            session.detach()
        except frida.InvalidOperationError:
            pass
    if server is not None:
        (trial / 'server.stop').write_text('owned trial finished', encoding='utf8')
        try:
            server.wait(timeout=20)
        except subprocess.TimeoutExpired:
            job.terminate()
            server.wait(timeout=10)
    if job:
        deadline = time.monotonic() + 3
        while job.pids() and time.monotonic() < deadline:
            time.sleep(.05)
        if job.pids():
            job.terminate()
            time.sleep(.1)
        report['owned_job_empty'] = not job.pids()
        job.close()
    if desktop:
        report['desktop_closed'] = bool(U.CloseDesktop(desktop))
    if log:
        log.close()
    if server_log:
        server_log.close()
    report['input_desktop_unchanged'] = input_desktop() == input_before
    report['foreground_window_before'] = foreground_before
    report['foreground_window_after'] = U.GetForegroundWindow()
    report['foreground_window_unchanged'] = report['foreground_window_after'] == foreground_before
    report['original_EXE_sha256_unchanged'] = sha(original / 'x2_dx11.exe') == exe_sha
    report['natural_Friends_startup']=report.get('ok',False)
    report['no_character_selection_input']=True
    save(trial / 'result.json', report)
print(json.dumps(report, ensure_ascii=False), flush=True)
if not report['ok']:
    raise SystemExit(1)
