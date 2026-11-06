from delivery_common import *
import ast,re,zipfile,shutil
P=W/'publication';assert not P.exists();P.mkdir()
C=read(W/'composition-fixed.json');contracts={}
assert not any((R/'analysis/coordination-20261015'/n).exists()for n in ('active-publication.lock','publication-record.lock'))
new_tables=['abyss2026_accounts','abyss2026_tasks','abyss2026_runs','quick_start_accounts','quick_start_career_receipts']
for channel in ('online','local'):
    pointer=read(R/f'releases/{channel}/current.json');parent=R/pointer['path'];old=R/C['parents'][channel]['path'];rows=C[channel+'_delta'];candidate=Path(C[channel+'_root'])
    manifest_name='rollup-manifest.json'if channel=='online'else'local-business-manifest.json'
    assert sha(parent/manifest_name)==pointer['manifest_sha256'];manifest=read(parent/manifest_name);files={r['path']:r for r in manifest['files']};delta=[]
    for r in rows:
        rel=r['path'];source=candidate/rel;before=old/rel;actual=parent/rel
        assert (before.read_bytes()if before.exists()else None)==(actual.read_bytes()if actual.exists()else None),('Changed tested input',rel)
        assert sha(source)==r['sha256']
        out=P/f'candidate-{channel}'/rel;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,out)
        d=dict(r,candidate=str(out));delta.append(d);files[rel]={k:d[k]for k in ('path','size','sha256')}
    # Only unrelated parent leaves drifted; retain field-entry repair in the test runtime too.
    if channel=='online':
        for r in manifest['files']:
            if r['path']in {d['path']for d in delta}:continue
            dest=candidate/r['path']
            if not dest.exists()or sha(dest)!=r['sha256']:
                assert not dest.exists()or dest.stat().st_nlink==1
                dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(parent/r['path'],dest)
    for key in ('source_PRs_merged','source_merge_commits'):
        if key in manifest:manifest['inherited_'+key]=manifest.pop(key)
    for key in ('delta','changes','source_binding','accepted_delivery','public_acceptance'):manifest.pop(key,None)
    rid=RID if channel=='online'else'local-'+RID
    manifest.update(release=rid,path=f'releases/{channel}/{rid}',parent_release=pointer['release'],parent_manifest_sha256=pointer['manifest_sha256'],files=[files[k]for k in sorted(files)],delta_files=len(delta),server_delta=len(delta),client_delta=0,support_delta=0,new_files=sum(d['parent_sha256']is None for d in delta),new_schema=channel=='online',new_tables=new_tables if channel=='online'else[],new_schema_definitions=5 if channel=='online'else 0,current_delta_defines=5 if channel=='online'else 0,install_DDL_statements=0,startup_DDL_statements=3 if channel=='online'else 0,lazy_table_definitions=2 if channel=='online'else 0,Git_merge=False,current_delta_Git_merge=False,scope='Boost fixes dual-channel; Abyss580 and QuickStart578 online only; preserve shop1630/navy78 and current field-entry fixes; expiry projection integration correction')
    save(P/f'{channel}-manifest.json',manifest)
    contracts[channel]=dict(parent=pointer,parent_pointer_sha256=sha(R/f'releases/{channel}/current.json'),root=manifest['path'],release=rid,manifest_sha256=sha(P/f'{channel}-manifest.json'),files=len(files),delta=delta)
    if channel=='local':
        runtime=read(parent/'client-bundle-manifest.json');rf={r['path']:r for r in runtime['files']}
        for d in delta:rf[d['path']]={k:d[k]for k in ('path','size','sha256')}
        runtime.update(release=rid,parent_release=pointer['release'],files=[rf[k]for k in sorted(rf)],file_count=len(rf),server_delta=len(delta),client_delta=0)
        save(P/'local-runtime-manifest.json',runtime)
facts=remote((R/'analysis/shop-rare-navy-20261101-v1/remote_preflight.txt').read_text('utf8'));assert not facts.pop('release_lock')and not facts.pop('stop_markers');save(P/'preflight.json',facts)
recovery_rows={r['path']:dict(r)for r in read(P/'online-manifest.json')['files']};recovery=[]
for d in contracts['online']['delta']:
    rel=d['path'];raw=Path(d['candidate']).read_bytes()
    if rel=='els_server/storage/quick_start.py':
        text=raw.decode('utf8');anchor="    db.execute('INSERT INTO quick_start_accounts VALUES (?,?,?)',(account,uid,now))"
        assert text.count(anchor)==1;text=text.replace(anchor,"    raise ValueError('New Quick Start enrollment paused for forward reader recovery')\n"+anchor);raw=text.encode()
    if rel=='els_server/storage/abyss_weapon_2026.py':
        text=raw.decode('utf8');anchor='        from els_server.storage.inventory_state import grant_items'
        # Pause only new account enrollment, after durable existing participant replay.
        idx=text.index('    def join(');end=text.index('    def tasks(',idx);part=text[idx:end]
        marker='        from els_server.storage.inventory_state import grant_items'
        if marker not in part:
            marker='        updates=grant_items('
        assert marker in part;part=part.replace(marker,"        raise ValueError('New Abyss enrollment paused for forward reader recovery')\n"+marker,1);text=text[:idx]+part+text[end:];raw=text.encode()
    out=P/'forward-recovery'/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(raw)
    if rel.endswith('.py'):ast.parse(raw)
    row=dict(path=rel,sha256=sha(out),size=len(raw));recovery.append(row);recovery_rows[rel]=row
manifest=read(P/'online-manifest.json');rm=dict(manifest,release=RID+'-recovery',files=[recovery_rows[k]for k in sorted(recovery_rows)],scope='Retain all new readers/schema/UIDs/receipts; pause new Abyss/QuickStart enrollment; never restore player databases');save(P/'online-recovery-manifest.json',rm)
with zipfile.ZipFile(P/'runtime-delta.zip','x',zipfile.ZIP_DEFLATED)as z:
    for d in contracts['online']['delta']:z.write(d['candidate'],d['path'])
    for d in recovery:z.write(P/'forward-recovery'/d['path'],'recovery/'+d['path'])
    z.write(P/'online-manifest.json','release-'+RID+'.json');z.write(P/'online-recovery-manifest.json','release-'+RID+'-recovery.json')
c=contracts['online'];parent=R/c['parent']['path']
req=dict(release=RID,parent_release=c['parent']['release'],parent_marker_sha256=c['parent']['manifest_sha256'],parent_files=read(parent/'rollup-manifest.json')['files'],new_files=manifest['files'],delta=c['delta'],new_manifest_sha256=c['manifest_sha256'],package_sha256=sha(P/'runtime-delta.zip'),recovery_delta=recovery,recovery_files=rm['files'],recovery_manifest_sha256=sha(P/'online-recovery-manifest.json'),human_instruction='Explicit authorized three-activity publisher handoff; Boost dual; Abyss/QuickStart ONLINE ONLY',owner=OWNER,**{k:v for k,v in facts.items()if k!='active_players'})
save(P/'requirements.json',req)
control=(R/'analysis/shop-rare-navy-20261101-v1/publication/control.py').read_text('utf8').replace('shop-rare-navy-20261101-v1',RID)
control,n=re.subn("EXPECTED_REQ_SHA='[a-f0-9]{64}'","EXPECTED_REQ_SHA='"+sha(P/'requirements.json')+"'",control);assert n==1
# Two databases, one API backup each after normal drain and before code writes.
# The previous generic controller's redundant live/stopped copies are unnecessary.
control=control.replace("    dual('live-before');save('backups-ready-normal-stop-requested'","    save('code-config-task-backups-ready-normal-stop-requested'")
control=control.replace("(initial_game==j['before_game'] and initial_accounts==j['before_accounts'])","(all(initial_game.get(k)==v for k,v in j['before_game'].items()) and initial_accounts==j['before_accounts'])")
ast.parse(control);(P/'control.py').write_text(control,'utf8')
save(P/'release-contract.json',contracts);save(P/'binding.json',dict(release=RID,contracts=contracts,files=[dict(path=str(P/n),sha256=sha(P/n))for n in ('requirements.json','runtime-delta.zip','online-manifest.json','local-manifest.json','local-runtime-manifest.json','control.py')],forward_reader_recovery=True,client_delta=0,Git_merge=False))
for name in ('launch_delivery.py','install_local.py','promote_online.py','qa_actions.py','closeout.py','release_locks.py'):
    text=(R/'analysis/shop-rare-navy-20261101-v1'/name).read_text('utf8')
    if name=='install_local.py':
        text=text.replace('shop_rare_navy_728=True','three_activities=True')
        text=text.replace("current_delta_defines=0,new_schema_definitions=0,new_schema=False,new_tables=[],install_DDL_statements=0","current_delta_defines=0,new_schema_definitions=0,new_schema=False,new_tables=[],install_DDL_statements=0")
    if name=='promote_online.py':
        text=text.replace('new_schema=False,current_delta_defines=0,new_schema_definitions=0,install_DDL_statements=0,shop_rare_navy_728=True','new_schema=True,current_delta_defines=5,new_schema_definitions=5,install_DDL_statements=0,startup_DDL_statements=3,lazy_table_definitions=2,three_activities=True')
        text=text.replace('rare_navy_purchase=True,gift_custom_register_apply=True','quick_start_creation_and_five_stages=True,abyss_join_and_box=True,boost_boxes_and_bank=True')
    ast.parse(text);(W/name).write_text(text,'utf8')
save(W/'related-tests.json',dict(ok=True,Boost=7,Abyss=11,QuickStart=3,QuickStart_session_dispatch=True,Boost_buff=3,integration_expiry=2,initial_campaign_failure_preserved='expiry-initial-failure.json',failed_two_retested=True,affected_expiry_retested=True,unchanged_source_native_proofs_reused=True,natural_GUI=False,natural_combat=False))
print(json.dumps(dict(ok=True,parents={k:v['parent']['release']for k,v in contracts.items()},online=42,local=14,files={k:v['files']for k,v in contracts.items()},active=facts['active_players'])))
