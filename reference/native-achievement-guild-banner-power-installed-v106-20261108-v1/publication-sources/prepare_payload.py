"""Freeze the exact eight-file online delta and current-data recovery policy."""
from common import *
import ast,copy,shutil,zipfile
held();ci=read(W/'platform-CI.json');assert ci['required_checks_passed']and ci['head']==plan['source_head']
parent=plan['parent'];assert read(R/'releases/online/current.json')==parent
old=read(BASE/'rollup-manifest.json');assert sha(BASE/'rollup-manifest.json')==parent['manifest_sha256']
prior={row['path']:row for row in old['files']}
template=(R/'analysis/server-latency-20261106-v7/publication/preflight.py').read_text('utf8')
start=template.index("code='''");end=template.index('facts=remote(code',start)
namespace=dict(online=parent,manifest=old);exec(compile(template[start:end],'<reused-read-only-preflight>','exec'),namespace)
facts=remote(namespace['code'],timeout=180);assert facts['ok']and facts['config_sha256']==parent['configuration_sha256']
assert facts['free_bytes']>2*sum(facts['database_bytes'].values())+512*1024**2
save(P/'preflight.json',facts);save(P/'parent.json',parent)
binding=read(plan['candidate_manifest']);assert sha(plan['candidate_manifest'])==plan['candidate_manifest_sha256']
delta=[];rows=copy.deepcopy(prior)
for entry in binding['files']:
    name=entry['path'];p=C/name;assert sha(p)==entry['sha256']and prior.get(name,{}).get('sha256')==entry['parent_sha256']
    if p.suffix=='.py':ast.parse(p.read_bytes())
    row=dict(path=name,size=p.stat().st_size,sha256=sha(p),parent_sha256=entry['parent_sha256']);delta.append(row);rows[name]={k:row[k]for k in('path','size','sha256')}
assert len(delta)==8
m=copy.deepcopy(old)
for key in ('delta','changes','source_binding','accepted_delivery','public_acceptance','source_PRs','source_PR','source_head','source_merge_commit'):m.pop(key,None)
schema=plan['schema_delta'];m.update(release=RID,path='releases/online/'+RID,parent_release=parent['release'],parent_manifest_sha256=parent['manifest_sha256'],
    files=[rows[name]for name in sorted(rows)],file_count=len(rows),delta_files=len(delta),server_delta=sum(r['path'].startswith('els_server/')for r in delta),
    new_files=sum(r['parent_sha256']is None for r in delta),client_delta=0,support_delta=sum(not r['path'].startswith('els_server/')for r in delta),
    new_schema=False,new_tables=schema['new_tables'],new_schema_definitions=0,new_indexes=schema['new_indexes'],inherited_schema_definitions=old.get('inherited_schema_definitions',0)+old.get('new_schema_definitions',0),
    install_DDL_statements=0,startup_DDL_statements=0,startup_index_definitions=0,lazy_business_DDL=True,new_dependencies=False,configuration_delta=0,
    Git_merge=False,current_delta_Git_merge=False,source_Git_merged=False,source_submission_pending=False,source_PR=plan['source_PR'],source_head=plan['source_head'],
    current_delta_PR=plan['source_PR'],current_delta_head=plan['source_head'],source_archive=plan['source_archive'],unified_runtime=True,
    shared_runtime_archive_sha256=read(D/'build.json')['signed_bindings']['signedFriends']['archive']['sha256'],scope=plan['scope'],natural_GUI=False,natural_battle=False,player_database_restore=False)
save(P/'online-manifest.json',m);save(P/'online-recovery-manifest.json',dict(old,release=RID+'-recovery',scope='Prior code only before candidate startup. Once startup is requested retain new readers and forward-fix. Never restore databases.'))
recovery=[dict(path=r['path'],sha256=r['parent_sha256'],size=prior[r['path']]['size'])for r in delta if r['parent_sha256']is not None]
bundle=P/'runtime-delta.zip';assert not bundle.exists()
with zipfile.ZipFile(bundle,'x',zipfile.ZIP_DEFLATED)as z:
    for row in delta:z.write(C/row['path'],row['path'])
    for row in recovery:z.write(BASE/row['path'],'recovery/'+row['path'])
    z.write(P/'online-manifest.json','release-'+RID+'.json');z.write(P/'online-recovery-manifest.json','release-'+RID+'-recovery.json')
q=dict(release=RID,owner=OWNER,backup_directory='C:/ElsFriends/backups/'+RID,parent_release=parent['release'],parent_marker_sha256=parent['manifest_sha256'],parent_files=old['files'],new_files=m['files'],delta=delta,
    recovery_delta=recovery,recovery_files=old['files'],package_sha256=sha(bundle),new_manifest_sha256=sha(P/'online-manifest.json'),new_config_sha256=facts['config_sha256'],
    forward_recovery_after_candidate_start=True,**{k:facts[k]for k in('config_sha256','python_sha256','server_python','server_python_sha256','task_xml_sha256','game_database','accounts_database','gate_path','manager_pid','child_pid')})
save(P/'requirements.json',q)
controller=(R/'analysis/server-latency-20261106-v7/publication/controller_template.py').read_text('utf8')
assert controller.count('EXPECTED_REQUIREMENTS_SHA')==1;controller=controller.replace('EXPECTED_REQUIREMENTS_SHA',sha(P/'requirements.json')).replace('installing-exact-merged-source','installing-exact-authorized-source')
a=" temporary=path.with_name(path.name+'.'+RID+'.next');";assert controller.count(a)==1;controller=controller.replace(a," path.parent.mkdir(parents=True,exist_ok=True)\n"+a)
a="  target=B/'code'/row['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/row['path'],target)"
b="  source=R/row['path']\n  if row['parent_sha256']is None:assert not source.exists()\n  else:\n   target=B/'code'/row['path'];target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)"
assert controller.count(a)==1;controller=controller.replace(a,b)
a="data=archive.read(row['path']);assert hashlib.sha256(data).hexdigest()==row['sha256']and sha(R/row['path'])==row['parent_sha256']"
b="data=archive.read(row['path']);assert hashlib.sha256(data).hexdigest()==row['sha256']and (sha(R/row['path'])if(R/row['path']).exists()else None)==row['parent_sha256']"
assert controller.count(a)==1;controller=controller.replace(a,b)
a=" gm_stop();wait_drained()\n if fd is None:acquire()";b=" gm_stop();wait_drained()\n if j.get('candidate_start_requested'):\n  save('forward-recovery-required-new-readers-retained',player_database_restore=False)\n  raise RuntimeError('Candidate startup was requested: retain new readers and current data; forward repair is required')\n if fd is None:acquire()"
assert controller.count(a)==1;controller=controller.replace(a,b)
a="  assert sha(target)in(row['sha256'],row['parent_sha256']);assert sha(B/'code'/name)==row['parent_sha256'];atomic(target,(B/'code'/name).read_bytes())"
b="  if row['parent_sha256']is None:\n   assert sha(target)==row['sha256'];target.unlink()\n  else:\n   assert sha(target)in(row['sha256'],row['parent_sha256']);assert sha(B/'code'/name)==row['parent_sha256'];atomic(target,(B/'code'/name).read_bytes())"
assert controller.count(a)==1;controller=controller.replace(a,b)
a=" action('start');state=ready_wait();pid=state['pid'];";assert controller.count(a)==1;controller=controller.replace(a," j['candidate_start_requested']=True;save('candidate-start-requested-with-owned-admission-gate')\n"+a)
ast.parse(controller);(P/'control.py').write_bytes(controller.encode())
shutil.copyfile(W/'qa_remote_worker.py',P/'qa_remote_worker.py')
shutil.copyfile(W/'achievement_fixture.py',P/'achievement_fixture.py')
shutil.copyfile(R/'tools/owned_qa_cleanup.py',P/'owned_qa_cleanup.py')
shutil.copyfile(R/'analysis/server-latency-20261106-v7/publication/shared_snapshot.py',P/'shared_snapshot.py')
save(W/'publication-ready.json',dict(ok=True,parent=parent['release'],candidate_files=8,source_PR=plan['source_PR'],source_head=plan['source_head'],forward_recovery_after_candidate_start=True))
print(json.dumps(dict(ok=True,parent=parent['release'],delta=8,new_files=m['new_files'],files=len(rows),active_players=facts['active_players'],production_mutated=False)))
