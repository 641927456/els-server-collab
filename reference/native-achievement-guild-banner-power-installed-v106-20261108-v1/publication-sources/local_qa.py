"""Exercise the actual selected local backend with exactly two owned identities."""
from common import *
from contextlib import closing
import asyncio, datetime, ssl, sqlite3, subprocess, traceback

held()
loaded=read(P/'local-actual-loaded.json')
assert loaded['ok']and loaded['all_selected_components_verified']and loaded['local_IP']=='127.0.0.1'
runtime=Path(loaded['runtime']).resolve();current=read(R/'releases/local/current.json')
assert runtime==(R/current['path']).resolve()and current['unified_runtime']
sys.path[:0]=[str(runtime),str(runtime/'tools/pylibs'),str(W)]
from els_server.config import ServerConfig
from els_server.storage.characters import Characters
from els_server.friends_bridge import Bridge,BridgeConfig
from achievement_closure_client import scenario
import achievement_fixture,psutil

cfg=ServerConfig.load(Path(current['config']))
assert cfg.mode=='friends'and cfg.host=='127.0.0.1'and cfg.state_file.resolve()==Path(read(P/'local-parent-stores.private.json')['game']).resolve()
logs=Path(loaded['log_dir']).resolve()
assert logs.is_relative_to(R/'state/unified-server/runs')and not logs.is_symlink()and not logs.is_junction()
work=P/'local-owned-qa-v2';operation=RID+'-local-v2'
owned=load('closure_local_owned_qa',R/'tools/owned_qa_cleanup.py')
values=[]

def lease():
    held()
    assert read(R/'releases/local/current.json')==current
    process=psutil.Process(loaded['pid'])
    assert abs(int((process.create_time()+11644473600)*10000000)-loaded['created_filetime'])<10000
    ready=read(loaded['ready_file'])
    assert ready['pid']==loaded['pid']and ready['host']=='127.0.0.1'and ready['port']==cfg.port

def completed():
    lease();ids={value['account_id']for value in values};auth=set();finished=set();windows=[]
    started=read(work/'intent.json')['started_utc'];errors=[]
    for path in logs.glob('server.jsonl*'):
        size=path.stat().st_size;count=min(size,1024*1024)
        while True:
            offset=size-count
            with path.open('rb')as stream:stream.seek(offset);raw=stream.read(count)
            rows=[]
            for line in(raw.splitlines()[1:]if offset else raw.splitlines()):
                try:row=json.loads(line)
                except ValueError:continue
                if isinstance(row.get('time'),str):rows.append(row)
            if not offset or rows and min(row['time']for row in rows)<=started:break
            assert count<64*1024*1024,'Owned log intent boundary not covered'
            count=min(size,count*2)
        windows.append(dict(name=path.name,offset=offset,bytes=count))
        for row in rows:
            if row['time']<started:continue
            if row.get('event')=='authenticated'and row.get('account_id')in ids:auth.add(row['connection'])
            if row.get('event')=='connection_finished':finished.add(row['connection'])
            if row.get('event')in('worker_error','notification_error','connection_task_error'):
                errors.append(dict(event=row['event'],connection=row.get('connection')))
    owned.write(work/'own-log-windows.json',dict(windows=windows,owned_auth=len(auth),owned_finished=len(auth&finished),
        own_errors=[error for error in errors if error['connection']in auth]))
    return bool(windows)and auth<=finished

def barrier(ids):
    assert set(ids)=={value['account_id']for value in values}
    async def disabled():
        for value in values:
            bridge=Bridge(BridgeConfig(**value['bridge']))
            try:
                try:_,writer=await bridge.remote()
                except ValueError as error:assert'authentication'in str(error).lower()
                else:writer.close();await writer.wait_closed();raise AssertionError('Disabled owned identity authenticated')
            finally:await bridge.close()
    asyncio.run(disabled())
    return completed()

report=dict(ok=False,local_IP='127.0.0.1',actual_final_launcher_backend=True,
    same_authenticated_server=True,certificate_pinned=True,checks=[],natural_GUI=False,natural_battle=False)
cleanup=None
try:
    lease();assert not work.exists();work.mkdir()
    subprocess.run(['icacls.exe',str(work),'/inheritance:r','/grant:r','*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F'],
                   check=True,capture_output=True,timeout=20,creationflags=0x08000000)
    owned.write(work/'intent.json',dict(started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        operation=operation,owner_thread=OWNER,purpose='Two owned local native QA identities; no player controls or database restore.'))
    pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
    for index,letter in enumerate('AB'):
        identity=owned.create_owned_account(cfg.accounts_file,work,'qa1108cpg105loc2'+letter.lower(),operation,allocation_key=letter)
        value=dict(account_id=identity['id'],uid=None,character_name='CP105L'+letter,
            bridge=dict(host='127.0.0.1',port=cfg.port,name=identity['name'],token=identity['token'],certificate_sha256=pin))
        values.append(value);owned.write(work/'credentials.private.json',values)
        value['uid']=Characters(cfg.state_file,identity['id']).create(value['character_name'],(1,2)[index],operation+'-create-'+letter)['uid']
        owned.write(work/'credentials.private.json',values)
    achievement_fixture.seed(cfg.state_file,values)
    owned.write(work/'credentials.private.json',values)
    snapshot=lambda:achievement_fixture.snapshot(cfg.state_file,values)
    asyncio.run(scenario(values,snapshot,report))
    assert report['ok']
    report['sqlite_version']=sqlite3.sqlite_version
except BaseException:
    report.update(ok=False,error=traceback.format_exc())
finally:
    if values:
        try:
            cleanup=owned.cleanup_owned_accounts(cfg.accounts_file,cfg.state_file,work,operation,
                capacity=cfg.max_registered_accounts,barrier=barrier,lease_check=lease)
            assert cleanup['ok']
            report['own_worker_errors']=read(work/'own-log-windows.json')['own_errors']
            if report['own_worker_errors']:report['ok']=False
            for name in('credentials.private.json','accounts-before-cleanup.sqlite3','game-before-cleanup.sqlite3'):
                path=work/name
                if path.exists():
                    assert path.resolve().parent==work.resolve()and not path.is_symlink()and not path.is_junction()
                    path.unlink()
        except BaseException:report.update(ok=False,cleanup_error=traceback.format_exc())
    report['owned_QA_cleanup']=cleanup
    save(P/'local-public-acceptance.json',report)
    print(json.dumps(report,ensure_ascii=False))
raise SystemExit(not report['ok'])
