"""Bounded, persistent GM publication; normal drain and forward reader recovery."""
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import re,datetime,hashlib,json,os,secrets,shutil,sqlite3,subprocess,sys,time,urllib.request,zipfile

STAGE=Path('C:/ElsFriends-staging/native-pr771-gameplay-racing-20261103-v2')
ROOT=Path('C:/ElsFriends');BACKUP=ROOT/'backups/native-pr771-gameplay-racing-20261103-v2'
sys.stdout=(STAGE/'control.stdout').open('a',encoding='utf8',buffering=1)
sys.stderr=(STAGE/'control.stderr').open('a',encoding='utf8',buffering=1)
print('persistent-task-control-start '+datetime.datetime.now(datetime.timezone.utc).isoformat(),flush=True)
EXPECTED_REQ_SHA='f1154331a1a4bffa04d789ada1a6bd532597157687e6137b2c610c1a01917010'
assert Path(__file__).resolve()==STAGE/'control.py'
raw=(STAGE/'requirements.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==EXPECTED_REQ_SHA
REQ=json.loads(raw);RID=REQ['release'];MARKER='Independent bounded fixes maintenance '+RID
sys.path.insert(0,str(ROOT))
from els_server.config import ServerConfig
CFG=ServerConfig.load(ROOT/'config/friends-server.toml')
assert CFG.mode=='friends' and CFG.port==19400
assert CFG.state_file.resolve()==Path(REQ['game_database']).resolve() and CFG.accounts_file.resolve()==Path(REQ['accounts_database']).resolve()
key=(ROOT/'state/gm/access.key').read_text('ascii').strip()
lock=ROOT/'run/release.lock';lock_fd=None;lock_identity=None
config_written=False
j={'release':RID,'phase':'preflight','written':[],'stopped':False,'ready':False,'server_mutation_started':False,'player_database_restore':False}
J=STAGE/'journal.json'


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(phase,**kw):
    j.update(phase=phase,updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw)
    temp=J.with_suffix('.next');temp.write_text(json.dumps(j,ensure_ascii=True,indent=2),'utf8')
    # Windows readers/security scanners can briefly deny rename/delete sharing.
    for attempt in range(20):
        try:os.replace(temp,J);break
        except PermissionError:
            if attempt==19:raise
            time.sleep(.05+min(attempt,5)*.025)
    print(phase,flush=True)
def ps(code):
    r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',"$ErrorActionPreference='Stop';[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false);"+code],capture_output=True,timeout=30)
    if r.returncode:raise RuntimeError(r.stderr.decode('utf8','replace')[-1200:])
    return r.stdout.decode('utf-8-sig').strip()
def api(path):
    return json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18765'+path,headers={'X-GM-Key':key}),timeout=10))['result']
def aggregate(rows):return hashlib.sha256(json.dumps(sorted((r['path'],r['sha256'],r['size']) for r in rows),separators=(',',':')).encode()).hexdigest()
def mg_hash():
    files=[p for p in (ROOT/'gm_console').rglob('*') if p.is_file()]
    def row(p):
        assert not p.is_symlink() and not p.is_junction()
        return {'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p),'size':p.stat().st_size}
    with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(row,files))
    return len(rows),aggregate(rows)
def code_check(rows):
    for r in rows:
        p=ROOT/r['path'];assert p.is_file() and sha(p)==r['sha256'],r['path']
def acquire():
    global lock_fd,lock_identity
    lock_fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600);lock_identity=secrets.token_hex(24).encode();os.write(lock_fd,lock_identity);os.fsync(lock_fd)
def release():
    global lock_fd
    if lock_fd is None:return
    os.lseek(lock_fd,0,os.SEEK_SET);assert os.read(lock_fd,100)==lock_identity and lock.read_bytes()==lock_identity and os.fstat(lock_fd).st_ino==lock.stat().st_ino
    os.close(lock_fd);lock_fd=None;lock.unlink()
def stop_markers():
    for n in ('server.stop','gm.stop'):
        p=ROOT/'run'/n
        if p.exists():assert p.read_text('utf8')==MARKER,'Foreign stop marker'
        else:p.write_text(MARKER,'utf8')
def clear_markers():
    for n in ('server.stop','gm.stop'):
        p=ROOT/'run'/n
        if p.exists():assert p.read_text('utf8')==MARKER;p.unlink()
def drained():
    result=ps("$t=Get-ScheduledTask -TaskName ELS-Friends-Server; [pscustomobject]@{state=[string]$t.State;tcp=@(Get-NetTCPConnection -LocalPort 19400,19401,18765,18766 -State Listen -ErrorAction SilentlyContinue).Count;udp=@(Get-NetUDPEndpoint -LocalPort 19401 -ErrorAction SilentlyContinue).Count;old=@(Get-CimInstance Win32_Process | Where-Object {$_.ProcessId -in @("+str(REQ['manager_pid'])+','+str(REQ['child_pid'])+")}).Count} | ConvertTo-Json -Compress")
    d=json.loads(result);return d['state']!='Running' and d['tcp']==0 and d['udp']==0 and d['old']==0
def wait_drain():
    end=time.monotonic()+180
    while time.monotonic()<end:
        if drained():return
        time.sleep(.5)
    raise RuntimeError('Normal drain unconfirmed; do not force-kill')
def copy_db(source,destination):
    assert not destination.exists()
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=5)) as src,closing(sqlite3.connect(destination)) as dst:
        src.execute('BEGIN');src.execute('SELECT count(*) FROM sqlite_master').fetchone()
        page=src.execute('PRAGMA page_size').fetchone()[0];snapshot_pages=src.execute('PRAGMA page_count').fetchone()[0]
        assert page*snapshot_pages < shutil.disk_usage(destination.parent).free,'Insufficient space for the measured backup snapshot'
        end=time.monotonic()+max(60,(page*snapshot_pages)/(8*1024*1024)+30)
        def bound(status,left,total):
            if total>snapshot_pages or time.monotonic()>end:raise RuntimeError('SQLite API backup snapshot size/time budget exceeded')
        src.backup(dst,pages=4096,progress=bound,sleep=.01)
        assert dst.execute('PRAGMA page_count').fetchone()[0]==snapshot_pages
        assert dst.execute('PRAGMA quick_check').fetchall()==[('ok',)]
def dual(name):
    d=BACKUP/name;d.mkdir()
    for n,p in [('game',CFG.state_file),('accounts',CFG.accounts_file)]:copy_db(p,d/(n+'.sqlite3'))
    return d
def history_counts(path):
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('BEGIN')
        return {name:db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ('inventory_action_receipts','activity518_facts','online2026_spans')}

def query_indexes():
    expected={'inventory_action_receipts_kind_owner':['kind','owner'], 'activity518_facts_account_period':['campaign','account','period'], 'activity518_facts_account_cursor':['campaign','account']}
    with closing(sqlite3.connect(CFG.state_file.as_uri()+'?mode=ro',uri=True)) as db:
        for name,columns in expected.items():assert [r[2]for r in db.execute('PRAGMA index_info('+name+')')]==columns,name
    return expected

def ready_wait():
    end=time.monotonic()+150
    while time.monotonic()<end:
        try:
            s=api('/api/status')
            if s['ready'] and s['owned'] and s['phase']=='running' and not lock.exists():return s
        except Exception:pass
        time.sleep(.5)
    raise RuntimeError('New manager/game did not become ready')
def start():
    clear_markers();release();ps('Start-ScheduledTask -TaskName ELS-Friends-Server');return ready_wait()
def health(expected_pid=None):
    s=api('/api/status');assert s['ready'] and s['owned'] and s['phase']=='running'
    if expected_pid:assert s['pid']==expected_pid,'Game unexpectedly restarted'
    assert sha(ROOT/'config/friends-server.toml')==REQ['new_config_sha256' if config_written else 'config_sha256']
    m=json.loads(ps("[pscustomobject]@{tcp=@(Get-NetTCPConnection -LocalPort 19400,18765,18766 -State Listen | Select-Object LocalPort,LocalAddress,OwningProcess);state=[string](Get-ScheduledTask -TaskName ELS-Friends-Server).State;feedback=(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:18080/ -TimeoutSec 8).StatusCode} | ConvertTo-Json -Depth 4"))
    assert m['state']=='Running' and m['feedback']==200 and len(m['tcp'])==3
    for r in m['tcp']:
        if r['LocalPort'] in (18765,18766):assert r['LocalAddress']=='127.0.0.1'
        if r['LocalPort'] in (19400,18766):assert r['OwningProcess']==s['pid']
    memory=json.loads(ps("$p=Get-Process -Id "+str(s['pid'])+";$o=Get-CimInstance Win32_OperatingSystem;[pscustomobject]@{working_set_bytes=$p.WorkingSet64;private_bytes=$p.PrivateMemorySize64;free_memory_kib=$o.FreePhysicalMemory;total_memory_kib=$o.TotalVisibleMemorySize}|ConvertTo-Json -Compress"))
    j.setdefault('memory_samples',[]).append(memory)
    return s,m
def restore():
    global config_written
    save('failure-recovering-code-config-service')
    stop_markers();wait_drain()
    if lock_fd is None:acquire()
    for row in REQ['delta']:
        target=ROOT/row['path']
        if row['parent_sha256'] is None and target.exists():
            assert sha(target)==row['sha256'];target.unlink()
    with zipfile.ZipFile(STAGE/'runtime-delta.zip')as archive:
        for row in REQ['recovery_delta']:
            raw=archive.read('recovery/'+row['path']);assert hashlib.sha256(raw).hexdigest()==row['sha256']
            (ROOT/row['path']).write_bytes(raw)
    shutil.copy2(BACKUP/'config.toml',ROOT/'config/friends-server.toml');config_written=False
    code_check(REQ['recovery_files'])
    s=start();pid=s['pid'];health(pid);begun=time.monotonic()
    while time.monotonic()-begun<120:health(pid);time.sleep(5)
    save('old-code-config-recovery-service-ready',ready=True,recovered_pid=pid,recovery_observation_seconds=time.monotonic()-begun)



try:
    assert sha(ROOT/('release-'+REQ['parent_release']+'.json'))==REQ['parent_marker_sha256']
    assert sha(ROOT/'config/friends-server.toml')==REQ['config_sha256'] and sha(ROOT/'python/python.exe')==REQ['python_sha256']
    assert sha(STAGE/'runtime-delta.zip')==REQ['package_sha256']
    assert sum(p.stat().st_size for p in STAGE.rglob('*') if p.is_file())<32*1024*1024
    assert shutil.disk_usage(ROOT).free>512*1024*1024
    assert not BACKUP.exists() and not any((ROOT/'run'/n).exists() for n in ('server.stop','gm.stop'))
    assert not lock.exists()
    save('parent-business-sha-verified-management-inventory-reading')
    pass # Management console is outside this server-only repair
    before=api('/api/status');assert before['ready'] and before['owned'] and before['pid']==REQ['child_pid']
    assert hashlib.sha256(ps('[string](Export-ScheduledTask -TaskName ELS-Friends-Server)').encode()).hexdigest()==REQ['task_xml_sha256']
    assert json.loads(ps("(Get-NetTCPConnection -LocalPort 18765 -State Listen).OwningProcess | ConvertTo-Json"))==REQ['manager_pid']
    acquire();code_check(REQ['parent_files'])
    assert sha(ROOT/('release-'+REQ['parent_release']+'.json'))==REQ['parent_marker_sha256']
    BACKUP.mkdir()
    # Keep credentials/DB/config backups inside Administrator/SYSTEM-only ACL.
    ps("$p='"+str(BACKUP)+"';$acl=New-Object Security.AccessControl.DirectorySecurity;$acl.SetAccessRuleProtection($true,$false);foreach($s in @('S-1-5-32-544','S-1-5-18')){$i=New-Object Security.Principal.SecurityIdentifier($s);$r=New-Object Security.AccessControl.FileSystemAccessRule($i,'FullControl','ContainerInherit,ObjectInherit','None','Allow');$acl.AddAccessRule($r)|Out-Null};Set-Acl -LiteralPath $p -AclObject $acl")
    (BACKUP/'task.xml').write_text(ps('[string](Export-ScheduledTask -TaskName ELS-Friends-Server)'),'utf8')
    shutil.copy2(ROOT/'config/friends-server.toml',BACKUP/'config.toml')
    for r in REQ['delta']:
        p=ROOT/r['path'];assert (sha(p) if p.is_file() else None)==r['parent_sha256']
        if p.is_file():d=BACKUP/'code'/r['path'];d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,d)
    gm=BACKUP/'gm-private';gm.mkdir()
    for n in ('access.key','desired.json','rates.json','events.json','audit.sqlite3'):
        p=ROOT/'state/gm'/n
        if p.is_file():copy_db(p,gm/n) if n.endswith('.sqlite3') else shutil.copy2(p,gm/n)
    save('code-config-task-backups-ready-normal-stop-requested',server_mutation_started=True,prior_active=len(before['players']))
    save('online-sqlite-backup-api-running');dual('online-before')
    j['stopped']=True;stop_markers();wait_drain();save('task-and-listeners-normally-drained')
    stopped=dual('stopped-before');j['before_history_counts']=history_counts(stopped/'game.sqlite3')
    save('stopped-backups-and-history-counts-ready')
    with zipfile.ZipFile(STAGE/'runtime-delta.zip') as z:
        assert z.testzip() is None
        expected={r['path'] for r in REQ['delta']}|{'release-'+RID+'.json'}|{'recovery/'+r['path']for r in REQ['recovery_delta']}|{'release-'+RID+'-recovery.json'};assert set(z.namelist())==expected
        for r in REQ['delta']:
            raw=z.read(r['path']);assert hashlib.sha256(raw).hexdigest()==r['sha256']
            p=ROOT/r['path'];p.parent.mkdir(parents=True,exist_ok=True)
            assert (sha(p) if p.exists() else None)==r['parent_sha256'];j['written'].append(r['path']);save('installing-exact-increment')
            p.write_bytes(raw)
        (ROOT/('release-'+RID+'.json')).write_bytes(z.read('release-'+RID+'.json'))
    assert sha(ROOT/'config/friends-server.toml')==REQ['config_sha256']
    code_check(REQ['new_files']);pass # Management console is outside this server-only repair
    save('installed-sha-verified-artifact-check')
    checked=subprocess.run([str(ROOT/'python/python.exe'),'-B','-m','els_server','--config',str(ROOT/'config/friends-server.toml'),'--check'],cwd=ROOT,capture_output=True,timeout=180)
    j['artifact_check']={'exit_code':checked.returncode,'stdout':checked.stdout.decode('utf8','replace'),'stderr':checked.stderr.decode('utf8','replace')};assert checked.returncode==0,'Installed artifact check'
    assert history_counts(CFG.state_file)==j['before_history_counts'],'Artifact check changed append-only history counts'
    save('installed-artifact-passed-starting-original-task');s=start();pid=s['pid'];save('candidate-game-ready-observing-120-seconds',ready=True,new_pid=pid)
    j['query_indexes_verified']=query_indexes()
    initial=history_counts(CFG.state_file)
    j['history_counts_not_regressed']=all(initial[k]>=v for k,v in j['before_history_counts'].items())
    assert j['history_counts_not_regressed']
    begun=time.monotonic()
    while time.monotonic()-begun<120:
        health(pid);save('candidate-game-ready-observing-120-seconds',observed_seconds=round(time.monotonic()-begun,1));time.sleep(5)
    state,meta=health(pid);save('awaiting-public-acceptance',observation_seconds=time.monotonic()-begun,final_status={k:state[k] for k in ('phase','ready','owned','pid','game_host','game_port')},feedback200=meta['feedback']==200)
except BaseException as e:
    j['failure']=repr(e)
    try:save('publication-failed-before-recovery')
    except BaseException as journal_error:print('failure journal unavailable: '+repr(journal_error),flush=True)
    if j['stopped']:
        try:restore()
        except BaseException as recovery_error:save('recovery-needs-attention',recovery_error=repr(recovery_error));raise
    else:release();save('preflight-failed-service-untouched')
    raise
finally:
    release()
