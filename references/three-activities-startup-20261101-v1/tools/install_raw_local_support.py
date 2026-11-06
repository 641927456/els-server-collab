from delivery_common import *
from contextlib import closing
import shutil,sqlite3,time,os,subprocess
P=W/'publication';D=W/'raw-local-support';assert not D.exists();D.mkdir()
h=read(P/'reservation.json')
def lease():
 for n,ino in h['inodes'].items():
  p=R/'analysis/coordination-20261015'/n;assert p.stat().st_ino==ino and read(p)==h['identity']
lease();pointer_path=R/'releases/local/current.json';pointer=read(pointer_path);assert pointer['release']=='local-three-activities-integrated-20261101-v1';parent=R/pointer['path']
assert read(P/'local-install/qualification.json')['ok'];assert read(W/'public-ui-frame-proof.json')['ok']
runtime=read(parent/'client-bundle-manifest.json');business=read(parent/'local-business-manifest.json')
rid='local-three-activities-startup-ui-20261101-v1';target=R/'releases/local'/rid;assert not target.exists();target.mkdir()
UI=R/'analysis/startup-ui-hide-20261101-v1';manifest=read(UI/'update-delta-manifest.json')['modes']['local'];delta={}
for r in manifest['files']:
 rel=r['path']
 if rel.endswith('client_compatibility_profiles.json'):continue
 src=UI/'update-delta/local'/rel;assert sha(src)==r['sha256'];assert (sha(parent/rel)if(parent/rel).exists()else None)==r['parent_sha256'];delta[rel]=src.read_bytes()
profile=read(parent/'tools/client_compatibility_profiles.json');before=read(parent/'tools/client_compatibility_profiles.json');entries=profile['profiles'][0]['artifacts']
for rel,raw in delta.items():entries[rel]=__import__('hashlib').sha256(raw).hexdigest()
assert {k for k in set(entries)|set(before['profiles'][0]['artifacts'])if entries.get(k)!=before['profiles'][0]['artifacts'].get(k)}==set(delta)
delta['tools/client_compatibility_profiles.json']=(json.dumps(profile,ensure_ascii=False,indent=2)+'\n').encode()
assert len(delta)==4
rows={r['path']:dict(r)for r in runtime['files']};br={r['path']:dict(r)for r in business['files']};changes=[]
for rel,raw in delta.items():
 out=D/'delta'/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw);row=dict(path=rel,sha256=sha(out),size=len(raw));rows[rel]=row;br[rel]=row;changes.append(dict(row,parent_sha256=sha(parent/rel)if(parent/rel).exists()else None))
for rel,row in rows.items():
 out=target/rel;out.parent.mkdir(parents=True,exist_ok=True)
 if rel in delta:out.write_bytes(delta[rel])
 else:shutil.copy2(parent/rel,out)
 assert out.stat().st_size==row['size']and sha(out)==row['sha256']
for m in (runtime,business):
 m.update(release=rid,parent_release=pointer['release'],parent_manifest_sha256=pointer['manifest_sha256'],delta_files=4,server_delta=0,support_delta=4,client_delta=0,new_files=2,new_schema=False,new_tables=[],new_schema_definitions=0,current_delta_defines=0,install_DDL_statements=0,Git_merge=False,current_delta_Git_merge=False,scope='Only startup UI support closure; all current Boost/shop/field/gate server bytes preserved; LOCAL profile mode differences retained')
runtime.update(files=[rows[k]for k in sorted(rows)],file_count=len(rows));business.update(files=[br[k]for k in sorted(br)])
save(target/'client-bundle-manifest.json',runtime);save(target/'local-business-manifest.json',business)
save(target/'release-snapshot.json',dict(release=rid,channel='local',local_business_manifest_sha256=sha(target/'local-business-manifest.json'),player_database_restore=False))
u=load('activities_raw_support_updater',R/'analysis/git-dual-delivery-20261030-v1/owned-stones-nine-leaf-execution-source-v5/execution/local-preparation/local_updater.py')
cfg,dbs,game=u.config_paths(target,R);backup=D/'backup';backup.mkdir()
for db in dbs:
 destination=backup/('game.sqlite3'if db==game else'accounts.sqlite3');end=time.monotonic()+45
 with closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True))as src,closing(sqlite3.connect(destination))as dst:
  src.execute('BEGIN');src.execute('SELECT count(*) FROM sqlite_master').fetchone()
  def bound(*args):assert time.monotonic()<end
  src.backup(dst,pages=128,progress=bound);assert dst.execute('PRAGMA quick_check').fetchall()==[('ok',)]
shutil.copy2(pointer_path,backup/'current.json');shutil.copy2(parent/'config/server.toml',backup/'server.toml')
# Only support changed. Reuse the actual same-server 120sec observation and
# identical LOCAL Hook/trace/dependency lifecycle; verify the new selected root.
server_paths=[r['path']for r in business['files']if r['path'].startswith('els_server/')]
assert all(sha(parent/n)==sha(target/n)for n in server_paths)
previous=R/'releases/local/local-registered-ground-items-20261101-v1'
assert sha(parent/'tools/trace_dx11_login.js')==sha(previous/'tools/trace_dx11_login.js')==manifest['trace_sha256_unchanged']
tools=target/'tools';code="from pathlib import Path;import sys,hashlib;sys.path[:0]=[sys.argv[1],sys.argv[2]];import native_cache_sync;root=Path(sys.argv[2]);s=native_cache_sync.compose((root/'analysis/client-6c6b5180/x2-runtime.bin').read_bytes(),native_cache_sync.EXE_SHA,(root/'tools/trace_dx11_login.js').read_text('utf8'));assert hashlib.sha256(s.encode()).hexdigest()==sys.argv[3];print('Exact LOCAL UI composition reused')"
q=subprocess.run([str(target/'python/python.exe'),'-B','-c',code,str(tools),str(target),manifest['composed_source_sha256']],capture_output=True,timeout=60,creationflags=0x08000000);assert q.returncode==0,q.stderr.decode('utf8','replace')[-1200:]
q=subprocess.run([str(target/'python/python.exe'),'-B',str(target/'tools/launch_client.py'),'--mode','local','--check'],cwd=target,capture_output=True,timeout=120,creationflags=0x08000000);assert q.returncode==0,q.stderr.decode('utf8','replace')[-1200:]
save(D/'qualification.json',dict(ok=True,delta=changes,runtime_files=len(rows),business_files=len(br),all_server_bytes_unchanged=True,server_observation_reused=str(P/'local-install/qualification.json'),LOCAL_lifecycle_reused=str(UI/'live-trial-8/result.json'),exact_LOCAL_composition_sha256=manifest['composed_source_sha256'],formal_LOCAL_entry_check=True,dual_SQLite_API_backups=True,player_database_restore=False))
new=dict(pointer,release=rid,path=target.relative_to(R).as_posix(),parent_release=pointer['release'],parent_manifest_sha256=pointer['manifest_sha256'],manifest_sha256=sha(target/'local-business-manifest.json'),delta_files=4,server_delta=0,support_delta=4,client_delta=0,new_files=2,business_files_verified=len(br),runtime_files_verified=len(rows),startup_ui_support=True,backup=str(backup),acceptance=str(D/'qualification.json'),current_delta_PR=None,current_delta_head=None,current_delta_Git_merge=False,scope=business['scope'])
lease();assert read(pointer_path)==pointer;temp=pointer_path.with_suffix('.ui-next');save(temp,new);os.replace(temp,pointer_path);save(target/'acceptance.json',new)
# Rebind this still-owned lease to the deliberate, verified LOCAL-only support
# installation. Preserve its earlier runtime pins as evidence of the transition.
reservation=W/'launcher-v60/publication/reservation.json';old=read(reservation);save(D/'launcher-reservation-before-support.json',old)
old['runtime_pins'][str(pointer_path)]=sha(pointer_path);old['LOCAL_support_addendum']=dict(path=str(D/'qualification.json'),sha256=sha(D/'qualification.json'));save(reservation,old)
save(D/'installation.json',dict(ok=True,release=rid,server_delta=0,support_delta=4,runtime_files=len(rows),business_files=len(br),pointer=new))
print(json.dumps(dict(ok=True,release=rid,support_delta=4,server_delta=0,runtime=len(rows),business=len(br),exact_LOCAL_composition=True,normal_LOCAL_entry_check=True)))
