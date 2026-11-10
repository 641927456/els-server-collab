from pathlib import Path
from contextlib import closing
import asyncio,datetime,hashlib,importlib.util,json,ssl,sqlite3,subprocess,sys,urllib.request
S=Path(__file__).resolve().parent;R=Path('C:/ElsFriends');sys.path[:0]=[str(R),str(S)];sys.dont_write_bytecode=True
RID='native-achievement-guild-banner-power-20261108-v1';work=R/'backups'/(RID+'-qa')
spec=importlib.util.spec_from_file_location('own_cleanup',S/'owned_qa_cleanup.py');owned=importlib.util.module_from_spec(spec);spec.loader.exec_module(owned)
from els_server.config import ServerConfig
from els_server.friends_bridge import Bridge,BridgeConfig
cfg=ServerConfig.load(R/'config/friends-server.toml');q=json.loads((S/'requirements.json').read_bytes());key=(R/'state/gm/access.key').read_text('ascii').strip()
def api():return json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18765/api/status',headers={'X-GM-Key':key}),timeout=10))['result']
sys.path.insert(0,str(S))
from shared_snapshot import snapshot

def lease():
 j=json.loads(snapshot(S/'journal.json'));assert j['phase']in('installed-and-stopped','candidate-game-ready-observing-120-seconds','awaiting-public-acceptance')and not j.get('failure')
 assert hashlib.sha256((R/('release-'+q['release']+'.json')).read_bytes()).hexdigest()==q['new_manifest_sha256']
 for row in q['delta']:assert hashlib.sha256((R/row['path']).read_bytes()).hexdigest()==row['sha256']
 state=api()
 if sys.argv[1]in('prepare','resume'):assert not state['ready']and state['phase']=='stopped'and state['pid']is None
 else:assert state['ready']and state['owned']and state['pid']==j['new_pid']

def creds():return json.loads((work/'credentials.private.json').read_bytes())
def completed():
 ids={c['account_id']for c in creds()};auth=set();done=set();errors=[]
 started=json.loads((work/'intent.json').read_bytes())['started_utc']
 since=datetime.datetime.fromisoformat(started).timestamp();windows=[]
 for p in cfg.log_dir.glob('server.jsonl*'):
  size=p.stat().st_size
  if p.stat().st_mtime<since:continue
  count=min(size,1024*1024)
  while True:
   offset=size-count
   with p.open('rb')as stream:stream.seek(offset);raw=stream.read(count)
   lines=raw.splitlines()[1:]if offset else raw.splitlines();rows=[]
   for line in lines:
    try:r=json.loads(line)
    except ValueError:continue
    if isinstance(r.get('time'),str):rows.append(r)
   if not offset or rows and min(r['time']for r in rows)<=started:break
   if count>=64*1024*1024:raise RuntimeError('Owned QA log intent boundary not covered')
   count=min(size,count*2)
  windows.append(dict(name=p.name,offset=offset,bytes=count))
  for r in rows:
   if r['time']<started:continue
   if r.get('event')=='authenticated'and r.get('account_id')in ids:auth.add(r['connection'])
   if r.get('event')=='connection_finished':done.add(r['connection'])
   if r.get('event')in('worker_error','notification_error','connection_task_error'):errors.append(dict(event=r['event'],connection=r.get('connection')))
 owned.write(work/'own-log-windows.json',dict(windows=windows,owned_auth=len(auth),owned_finished=len(auth&done),own_errors=[error for error in errors if error['connection']in auth]))
 return bool(windows)and auth<=done and not any(p.get('account_id')in ids for p in api()['players'])
def barrier(ids):
 lease();assert set(ids)=={c['account_id']for c in creds()}
 async def check():
  for c in creds():
   b=Bridge(BridgeConfig(**c['bridge']))
   try:
    try:_,w=await b.remote()
    except ValueError as e:assert'authentication'in str(e).lower()
    else:w.close();await w.wait_closed();raise AssertionError('Disabled owned identity authenticated')
   finally:await b.close()
 asyncio.run(check());return completed()


def main():
 action=sys.argv[1];lease()
 if action in('prepare','resume'):
  if action=='prepare':
   assert not work.exists();work.mkdir()
   subprocess.run(['icacls.exe',str(work),'/inheritance:r','/grant:r','*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F'],check=True,capture_output=True,timeout=20)
   owned.write(work/'intent.json',dict(started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),operation=RID,purpose='Two owned QA accounts and one same-account alternative; level99, ED and one creation license are explicit fixtures. Normal guild creation/invite/accept, four banner display paths, accepted toggles, native CP payload boundary and cold account sharing. No natural GUI, battle or gear acquisition.'))
  else:
   assert json.loads((work/'intent.json').read_bytes())['operation']==RID
   assert {p.name for p in work.iterdir()}=={'intent.json'}
   with closing(sqlite3.connect(cfg.accounts_file.as_uri()+'?mode=ro',uri=True))as db:
    assert not db.execute('SELECT id FROM accounts WHERE name IN (?,?)',('qa1108cpg105a','qa1108cpg105b')).fetchall()
  from els_server.storage.characters import Characters
  import achievement_fixture
  pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
  values=[]
  for index,letter in enumerate(('A','B')):
   account=owned.create_owned_account(cfg.accounts_file,work,'qa1108cpg105'+letter.lower(),RID,allocation_key=letter)
   value=dict(account_id=account['id'],uid=None,character_name='CPG105'+letter,bridge=dict(host='134.175.57.52',port=19400,name=account['name'],token=account['token'],certificate_sha256=pin))
   values.append(value);owned.write(work/'credentials.private.json',values)
   value['uid']=Characters(cfg.state_file,account['id']).create(value['character_name'],(1,2)[index],RID+'-create-'+letter)['uid'];owned.write(work/'credentials.private.json',values)
  achievement_fixture.seed(cfg.state_file,values);owned.write(work/'credentials.private.json',values)
  owned.write(work/'fixture.json',dict(owned_accounts=2,owned_characters=3,guild_banner_CP_owned_fixtures=True,natural_GUI=False,natural_acquisition=False,natural_battle=False))
  print(json.dumps(values))
 elif action=='snapshot':
  import achievement_fixture
  print(json.dumps(achievement_fixture.snapshot(cfg.state_file,creds())))
 elif action=='cleanup':
  assert completed(),'Owned connections still present'
  print(json.dumps(owned.cleanup_owned_accounts(cfg.accounts_file,cfg.state_file,work,RID,capacity=cfg.max_registered_accounts,barrier=barrier,lease_check=lease)))
 elif action=='status':
  done=completed();print(json.dumps(dict(own_connections_completed=done,own_errors=json.loads((work/'own-log-windows.json').read_bytes())['own_errors'])))
 else:raise ValueError(action)
if __name__=='__main__':main()
