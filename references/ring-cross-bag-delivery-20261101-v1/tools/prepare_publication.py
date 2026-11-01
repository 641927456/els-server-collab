from delivery_common import *
import ast,re,shutil,zipfile
A=R/'analysis/ring-wear-error-20261101-v1';B=R/'analysis/queued-activities-delivery-20261101-v1';P=W/'publication';assert not P.exists()
# The preceding publisher returns this exact independent slot before binding.
handoff=read(W/'preceding-publisher-handoff.json');assert handoff['slot_returned_to_ring']and handoff['verified_direct_message']
assert not any((R/'analysis/coordination-20261015'/n).exists()for n in ('active-publication.lock','publication-record.lock'))
P.mkdir();source=read(A/'result-v2.json');contracts={}
for channel in ('online','local'):
 pointer=read(R/'releases'/channel/'current.json');parent=R/pointer['path'];name='rollup-manifest.json'if channel=='online'else'local-business-manifest.json';assert sha(parent/name)==pointer['manifest_sha256']
 m=read(parent/name);files={r['path']:r for r in m['files']};delta=[]
 for row in source['runtime_files']:
  rel=row['path'];src=W/'candidate'/rel;assert sha(src)==row['sha256'];assert sha(parent/rel)==row['parent_sha256'][channel],('Selective rebase required',rel)
  dest=P/f'candidate-{channel}'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest);d=dict(path=rel,size=dest.stat().st_size,sha256=sha(dest),parent_sha256=sha(parent/rel),candidate=str(dest));delta.append(d);files[rel]={k:d[k]for k in ('path','size','sha256')}
 for key in ('source_PRs_merged','source_merge_commits'):
  if key in m:m['inherited_'+key]=m.pop(key)
 for key in ('delta','changes','source_binding','accepted_delivery','public_acceptance'):m.pop(key,None)
 rid=RID if channel=='online'else'local-'+RID
 m.update(release=rid,path=f'releases/{channel}/{rid}',parent_release=pointer['release'],parent_manifest_sha256=pointer['manifest_sha256'],files=[files[k]for k in sorted(files)],delta_files=2,server_delta=2,client_delta=0,support_delta=0,new_files=0,new_schema=False,new_tables=[],new_schema_definitions=0,current_delta_defines=0,install_DDL_statements=0,startup_DDL_statements=0,lazy_table_definitions=0,Git_merge=False,current_delta_Git_merge=False,scope='Shared costume-tab replacement and retained helper; old item returns to its native7/27 tab atomically, three-position105/receipt replay; retain latest labyrinth/V61, activities, shop and UI support',wear_receipt_format='Existing two positions and new optional third native-return position; retain complete readers on recovery')
 save(P/f'{channel}-manifest.json',m);contracts[channel]=dict(parent=pointer,parent_pointer_sha256=sha(R/'releases'/channel/'current.json'),root=m['path'],release=rid,manifest_sha256=sha(P/f'{channel}-manifest.json'),files=len(files),delta=delta)
 if channel=='local':
  runtime=read(parent/'client-bundle-manifest.json');rf={r['path']:r for r in runtime['files']}
  for d in delta:rf[d['path']]={k:d[k]for k in ('path','size','sha256')}
  runtime.update(release=rid,parent_release=pointer['release'],files=[rf[k]for k in sorted(rf)],file_count=len(rf),server_delta=2,support_delta=0,client_delta=0)
  save(P/'local-runtime-manifest.json',runtime)
facts=remote((R/'analysis/shop-rare-navy-20261101-v1/remote_preflight.txt').read_text('utf8'));assert not facts.pop('release_lock')and not facts.pop('stop_markers');save(P/'preflight.json',facts)
manifest=read(P/'online-manifest.json');rm=dict(manifest,release=RID+'-recovery',scope='Forward compatible three-position reader retained; only new cross-tab replacement paused; never restore player databases');rf={r['path']:dict(r)for r in rm['files']};recovery=[]
for d in contracts['online']['delta']:
 rel=d['path'];raw=Path(d['candidate']).read_bytes()
 if rel.endswith('/fashion_state.py'):
  text=raw.decode('utf8');needle=' return changes';assert text.count(needle)==1;text=text.replace(needle," if len(changes)>2:raise ValueError('Cross-tab replacement paused for forward reader recovery')\n"+needle);raw=text.encode()
 ast.parse(raw);out=P/'forward-recovery'/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw);row=dict(path=rel,size=len(raw),sha256=sha(out));recovery.append(row);rf[rel]=row
rm['files']=[rf[k]for k in sorted(rf)];save(P/'online-recovery-manifest.json',rm)
with zipfile.ZipFile(P/'runtime-delta.zip','x',zipfile.ZIP_DEFLATED)as z:
 for d in contracts['online']['delta']:z.write(d['candidate'],d['path'])
 for d in recovery:z.write(P/'forward-recovery'/d['path'],'recovery/'+d['path'])
 z.write(P/'online-manifest.json','release-'+RID+'.json');z.write(P/'online-recovery-manifest.json','release-'+RID+'-recovery.json')
c=contracts['online'];req=dict(release=RID,parent_release=c['parent']['release'],parent_marker_sha256=c['parent']['manifest_sha256'],parent_files=read(R/c['parent']['path']/'rollup-manifest.json')['files'],new_files=manifest['files'],delta=c['delta'],new_manifest_sha256=c['manifest_sha256'],package_sha256=sha(P/'runtime-delta.zip'),recovery_delta=recovery,recovery_files=rm['files'],recovery_manifest_sha256=sha(P/'online-recovery-manifest.json'),human_instruction='Explicit ring-wear source user handoff for Git and dual installation',owner=OWNER,**{k:v for k,v in facts.items()if k!='active_players'});save(P/'requirements.json',req)
control=(B/'publication/control.py').read_text('utf8').replace('three-activities-integrated-20261101-v1',RID);control,n=re.subn("EXPECTED_REQ_SHA='[a-f0-9]{64}'","EXPECTED_REQ_SHA='"+sha(P/'requirements.json')+"'",control);assert n==1;ast.parse(control);(P/'control.py').write_text(control,'utf8')
save(P/'release-contract.json',contracts);save(P/'binding.json',dict(release=RID,contracts=contracts,files=[dict(path=str(P/n),sha256=sha(P/n))for n in ('requirements.json','runtime-delta.zip','online-manifest.json','local-manifest.json','local-runtime-manifest.json','control.py')],forward_reader_recovery=True,client_delta=0,Git_merge=False))
for name in ('launch_delivery.py','install_local.py','promote_online.py','qa_actions.py','closeout.py','release_locks.py'):
 text=(B/name).read_text('utf8').replace('three_activities=True','cross_bag_wear=True')
 if name=='promote_online.py':
  text=text.replace('new_schema=True,current_delta_defines=5,new_schema_definitions=5','new_schema=False,current_delta_defines=0,new_schema_definitions=0').replace('startup_DDL_statements=3,lazy_table_definitions=2','startup_DDL_statements=0,lazy_table_definitions=0').replace('quick_start_creation_and_five_stages=True,abyss_join_and_box=True,boost_boxes_and_bank=True','cross_bag_wear_both_directions=True,three_position_receipt_reader=True')
 ast.parse(text);(W/name).write_text(text,'utf8')
print(json.dumps(dict(ok=True,dual_delta=2,new_schema=False,receipt_readers_preserved=True,parents={k:v['parent']['release']for k,v in contracts.items()},active_players=facts['active_players'])))
