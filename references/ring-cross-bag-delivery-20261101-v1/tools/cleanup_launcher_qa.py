from delivery_common import *
from contextlib import closing
import base64,os,stat,subprocess,sqlite3,tomllib
D=W/'launcher-v62';assert read(D/'publication/installation.json')['ok']and read(W/'public-native-verification.json')['ok']
boundary=load('ring_cleanup_boundary',R/'analysis/labyrinth-mechanisms-delivery-20261101-v1/launcher_cleanup_boundary.py')
typed=load('ring_cleanup_typed',R/'analysis/all-ground-item-models-20261101-v1/qualify_launcher_v59.py').typed
def run(argv):return subprocess.run(list(map(str,argv)),capture_output=True,check=True,creationflags=0x08000000)
def rows(build):
 ref=read(build)['signed_bindings']['signedLOCAL']['manifest'];return {r['path']:r for r in json.loads(base64.b64decode(read(ref['path'])['payload']))['files']}
for p in (D/'processes').glob('*.json'):
 q=read(p);assert q['ok']and q['Job_zero_closed']and not q['forced']
for p in (D/'publication/processes').glob('*.json'):
 q=read(p);assert q['ok']and q['Job_zero_closed']and not q['forced']
parent=read(W/'preceding-publisher-handoff.json')['parent_launcher_build'];oldrows=rows(parent);newrows=rows(D/'build.json')
prior=read(R/'analysis/queued-activities-delivery-20261101-v1/launcher-v60/build.json');priorrows={r['path']:r for r in json.loads(base64.b64decode(read(prior['signed_bindings']['signedLOCAL']['manifest']['path'])['payload']))['files']}
expected=list(read(D/'typed-private-before.json').values());plans=[]
for H in (R/'analysis/ring62p',R/'analysis/qa60u'):
 assert read(H/'owner.json')['thread']==OWNER
 paths=boundary.inventory(H);files=[p for p in paths if p.is_file()];catalogs={}
 rowsets=[oldrows,newrows,priorrows]
 for p in files:
  if p.name=='catalog.sqlite3':
   matches=[rs['els_server/data/client/catalog.sqlite3']for rs in rowsets if 'els_server/data/client/catalog.sqlite3'in rs and p.stat().st_size==rs['els_server/data/client/catalog.sqlite3']['size']and sha(p)==rs['els_server/data/client/catalog.sqlite3']['sha256']]
   assert matches,p;catalogs[p]=dict(kind='exact-signed-immutable-catalog',sha256=sha(p))
 repo=H/'p/r';catalogs.update(boundary.tracked_databases(repo,run))
 for p in files:
  if boundary.is_database(p)and p not in catalogs:
   value=typed(p)
   if value in expected:catalogs[p]=dict(kind='exact-owned-ring-probe-database',sha256=sha(p))
   else:
    assert p.name=='game.sqlite3'and p.parent.name=='smoke'and p.parent.parent.name in ('private-preflight','private-observation'),p
    journal=p.parents[2]/'journal.json';completion=p.parents[2]/'completion.json';j=read(journal);done=read(completion)
    assert j['phase']=='complete'and j['repository']==str(repo)and not j['parent']['player_database_imported']and j['candidate']['release']=='local-git-first-run-ring-wear-20261101-v1'
    assert done['ok']and done['original_typed_rows_and_schema_unchanged']and not done['player_database_restore']
    cfg=tomllib.loads((p.parent/'isolated-server.toml').read_text('utf8'))['server'];assert Path(cfg['state_file'])==p and cfg['mode']=='local'and cfg['host']=='127.0.0.1'and cfg['port']==0
    with closing(sqlite3.connect(p.as_uri()+'?mode=ro',uri=True))as db:
     assert db.execute('SELECT nonce,payload FROM owned_ring_launcher_probe').fetchall()==[(read(H/'owner.json')['nonce'],b'\x00ring62\xff')]
     assert all(aid<=1 for aid, in db.execute('SELECT account_id FROM character_owners'))
    for log in (p.parent/'logs').glob('*.jsonl'):
     assert all(json.loads(line).get('event')not in ('authenticated','character_selected')for line in log.read_text('utf8').splitlines())
    catalogs[p]=dict(kind='exact-owned-ring-smoke-database',sha256=sha(p),journal=str(journal),loopback_ephemeral_only=True)
 for p in files:
  base=boundary.sidecar_base(p)
  if base is not None:assert base in catalogs and catalogs[base]['kind']in ('exact-owned-ring-probe-database','exact-owned-ring-smoke-database'),p
  if 'state'in p.relative_to(H).parts and p not in catalogs and base is None:
   bound_lock=p.name.endswith('.sqlite3.lock')and p.with_name(p.name[:-5])in catalogs
   smoke_file=any(p.is_relative_to(db.parent)for db,row in catalogs.items()if row['kind']=='exact-owned-ring-smoke-database')
   recovery_lock=p.name=='repair-recovery-owner.lock'and p.parent==repo/'.runtime-cache/unified-local/state/local-updater'
   assert bound_lock or smoke_file or recovery_lock or p.name in ('friends-client.example.json','registration.example.json')or p.suffix=='.json',('Unclassified state',p)
 boundary.no_occupancy(files);plans.append((H,paths,catalogs))
save(D/'QA-cleanup-plan.json',dict(roots=[dict(root=str(h),files=sum(p.is_file()for p in paths),databases={str(p):v for p,v in catalogs.items()})for h,paths,catalogs in plans],same_thread_only=True,old_blocked_roots_excluded=True))
for H,paths,catalogs in plans:
 target=D/'retained-QA'/H.name;target.mkdir(parents=True)
 for rel in ('owner.json','p/owner.json'):
  src=H/rel;out=target/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(src.read_bytes());assert sha(out)==sha(src)
 for src in [*H.glob('*.json'),*(H/'p/results').glob('*.json')]:
  out=target/src.relative_to(H);out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(src.read_bytes());assert sha(out)==sha(src)
 for p in sorted(paths,key=lambda p:len(p.parts),reverse=True):
  if p.is_file():
   if p.stat().st_file_attributes&1:p.chmod(stat.S_IWRITE)
   p.unlink()
  else:p.rmdir()
 H.rmdir();assert not H.exists()
save(D/'QA-cleanup.json',dict(ok=True,roots_removed=[str(h)for h,_,_ in plans],typed_private_probe_databases_only=True,immutable_catalogs_verified=True,no_occupancy_verified=True,old_blocked_roots_excluded=True))
print('Exact owned public/private launcher QA roots cleaned')
