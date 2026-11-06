"""Install the single signed runtime selected by the trusted launcher."""
import argparse, hashlib, json, os, shutil, sqlite3, subprocess, sys, time, uuid
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from provision_unified_server import provision

def sha(path):
    with Path(path).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with tmp.open('x',encoding='utf8')as f:json.dump(value,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)
def backup(source,target):
    assert not target.exists()
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True))as src,closing(sqlite3.connect(target))as dst:
        src.backup(dst);assert dst.execute('PRAGMA quick_check').fetchall()==[('ok',)]
def under(root,name):
    rel=Path(name);assert not rel.is_absolute()and '..'not in rel.parts and ':'not in name
    path=root/rel;assert path.resolve().is_relative_to(root)
    for parent in [path,*path.parents]:
        if parent==root:break
        assert not parent.is_symlink()and not parent.is_junction()
    return path

def plain_absolute(path):
    path=Path(path)
    assert path.is_absolute()and Path(os.path.abspath(path))==path,'Noncanonical owned path'
    for parent in (path,*path.parents):
        assert not parent.is_symlink()and not parent.is_junction(),'Linked installation path'
    return path

def remove_owned_tree(path,boundary):
    path=plain_absolute(path);boundary=plain_absolute(boundary)
    assert path!=boundary and path.is_relative_to(boundary)
    assert all(not p.is_symlink()and not p.is_junction()for p in path.rglob('*'))
    shutil.rmtree(path)

def recover_dead_install(workspace):
    """Recover only this installer's exact dead transaction, never other locks."""
    import psutil
    paths=[workspace/'analysis/coordination-20261015'/n for n in ('active-publication.lock','publication-record.lock')]
    present=[p for p in paths if p.exists()]
    if not present:return
    for p in present:plain_absolute(p)
    documents=[json.loads(p.read_bytes())for p in present]
    identity=documents[0]
    if (identity.get('schema')!='els-unified-install-v1' or identity.get('operation')!='unified-server-install'):
        return  # A publisher/other installer owns this queue.
    assert all(d==identity for d in documents),'Publication owners disagree'
    assert identity['workspace']==str(workspace)and uuid.UUID(identity['token']).hex==identity['token']
    journal=plain_absolute(identity['journal'])
    assert journal.name=='journal.json'and journal.parent.parent==(workspace/'state/unified-installer').resolve()
    assert not journal.is_symlink()and not journal.parent.is_junction()
    data=json.loads(journal.read_bytes());assert data['identity']==identity
    try:
        process=psutil.Process(identity['pid'])
        assert process.create_time()!=identity['owner_created'],'The original installation is still running'
    except psutil.NoSuchProcess:pass
    # AccessDenied/unknown owner states deliberately do not permit recovery.
    observed={str(p):p.stat().st_ino for p in present}
    assert all(data['lock_inodes'].get(p.name)==observed[str(p)]for p in present),'Lock identity changed'
    pointer=workspace/'releases/local/current.json';current=json.loads(pointer.read_bytes())if pointer.exists()else None
    assert current==data['parent']or('candidate'in data and current==data['candidate']),'A different current blocks recovery'
    stage=plain_absolute(journal.parent/'runtime');destination=plain_absolute(data['destination'])
    assert destination.parent==(workspace/'releases/local').resolve()
    assert destination.name==data['release']and destination.name.startswith('unified-server-'+data['source_identity'][:16]+'-')
    # A check child can outlive a killed installer. Wait for its natural exit;
    # recovery never terminates a process or removes files still executing.
    for process in psutil.process_iter(['exe','cwd']):
        for value in (process.info.get('exe'),process.info.get('cwd')):
            if value:
                resolved=Path(value).resolve()
                assert not any(resolved==p or resolved.is_relative_to(p)for p in(stage,destination)),'An installation child still uses this runtime'
    if stage.exists():remove_owned_tree(stage,journal.parent)
    if current!=data.get('candidate')and destination.exists():
        assert sha(destination/'local-business-manifest.json')==data['manifest_sha256']
        remove_owned_tree(destination,workspace/'releases/local')
    private_stage=workspace/'state'/('unified-server.stage-'+identity['token'])
    if private_stage.exists():remove_owned_tree(private_stage,workspace/'state')
    data.update(phase='recovered-dead-owner',player_database_restore=False);save(journal,data)
    for p in present:
        assert p.stat().st_ino==observed[str(p)]and json.loads(p.read_bytes())==identity
        p.unlink()

def publication_locks(workspace,reservation,expected=None):
    """Use an explicitly delegated batch reservation without owning its locks."""
    import psutil
    document=json.loads(plain_absolute(reservation).read_bytes());owner=document['identity']
    if expected is not None:assert document==expected,'Publisher delegation changed'
    assert owner['operation']=='unified-server-publication'
    assert owner['thread']==os.environ['CODEX_THREAD_ID'] and owner['thread']
    assert psutil.Process(owner['pid']).create_time()==owner['owner_created'],'Publisher owner changed'
    for name in ('active-publication.lock','publication-record.lock'):
        path=plain_absolute(workspace/'analysis/coordination-20261015'/name)
        assert path.stat().st_ino==document['inodes'][name] and json.loads(path.read_bytes())==owner,'Publisher reservation changed'
    return document

def install(workspace,definition,publication=None):
    workspace=Path(workspace).resolve();rows=definition['files'];assert rows
    plain_absolute(workspace/'state');plain_absolute(workspace/'releases/local')
    # This is generated by ComponentRuntime after full signature/file checks;
    # every file is independently rehashed before copying or selecting it.
    names=set()
    for row in rows:
        name=row['path'];assert name not in names;names.add(name);p=under(ROOT,name)
        assert p.is_file()and p.stat().st_size==row['size']and sha(p)==row['sha256'],name
    assert {'python/python.exe','els_server/application.py','tools/run_unified_server.py'}<=names
    assert not any(n.startswith('state/')for n in names)
    assert not names&{'client-bundle-manifest.json','local-business-manifest.json','release-snapshot.json'},'Runtime payload contains installer-owned metadata'
    aggregate=hashlib.sha256(json.dumps(sorted((r['path'],r['size'],r['sha256'])for r in rows),separators=(',',':')).encode()).hexdigest()
    content_identity=hashlib.sha256('\n'.join(r['path']+'\t'+str(r['size'])+'\t'+r['sha256']for r in sorted(rows,key=lambda r:r['path'])).encode('utf8')).hexdigest()
    delegation=None
    if publication is None:recover_dead_install(workspace)
    else:delegation=publication_locks(workspace,publication)
    pointer=workspace/'releases/local/current.json'
    prior_raw=pointer.read_bytes()if pointer.exists()else None;prior=json.loads(prior_raw)if prior_raw else None
    if delegation is not None:assert prior==delegation['parents']['local'],'Publication local parent changed'
    if prior and prior.get('unified_runtime')and prior.get('shared_runtime_identity')==aggregate:
        destination=under(workspace,prior['path'])
        assert sha(destination/'client-bundle-manifest.json')==prior['runtime_manifest_sha256']
        for row in rows:assert sha(destination/row['path'])==row['sha256']
        return dict(ok=True,reused=True,release=prior['release'],workspace=str(workspace),runtime=str(destination))
    rid='unified-server-'+aggregate[:16]+'-'+uuid.uuid4().hex[:12]
    destination=workspace/'releases/local'/rid
    area=workspace/'state/unified-installer'/uuid.uuid4().hex;area.mkdir(parents=True)
    import psutil
    journal=area/'journal.json'
    locks=[];identity=dict(schema='els-unified-install-v1',operation='unified-server-install',workspace=str(workspace),pid=os.getpid(),owner_created=psutil.Process().create_time(),token=uuid.uuid4().hex,journal=str(journal))
    transaction=dict(identity=identity,parent=prior,release=rid,destination=str(destination),source_identity=aggregate,lock_inodes={},phase='acquiring')
    save(journal,transaction)
    try:
        for name in (() if publication is not None else ('active-publication.lock','publication-record.lock')):
            p=workspace/'analysis/coordination-20261015'/name;p.parent.mkdir(parents=True,exist_ok=True)
            with p.open('x',encoding='utf8')as f:json.dump(identity,f);f.flush();os.fsync(f.fileno())
            locks.append((p,p.stat().st_ino))
            transaction['lock_inodes'][name]=p.stat().st_ino;save(journal,transaction)
        transaction['phase']='locked';save(journal,transaction)
        assert (pointer.read_bytes()if pointer.exists()else None)==prior_raw,'Parent changed'
        assert not destination.exists(),'Foreign unselected release directory exists'
        game=workspace/'state/integrated.sqlite3'
        if prior:
            import tomllib
            if prior.get('unified_runtime'):
                oldconfig=Path(prior['config']).resolve()
                assert oldconfig.is_relative_to(workspace/'state'),'Foreign unified configuration'
                assert oldconfig.is_file(),'Selected unified configuration missing'
            else:oldconfig=under(workspace,prior['path'])/'config/server.toml'
            if oldconfig.exists():
                d=tomllib.loads(oldconfig.read_text('utf8'))['server'];game=(oldconfig.parent/d['state_file']).resolve()
                shutil.copy2(oldconfig,area/'prior-config.toml')
            assert game.is_relative_to(workspace/'state'),'Foreign legacy save'
            assert sha(under(workspace,prior['path'])/'local-business-manifest.json')==prior['manifest_sha256'],'Prior manifest changed'
            (area/'prior-current.json').write_bytes(prior_raw)
            # The old immutable code is kept until the explicit post-install
            # cleanup; this records its exact identity without duplicating it.
            shutil.copy2(under(workspace,prior['path'])/'local-business-manifest.json',area/'prior-business-manifest.json')
        if game.exists():backup(game,area/'game-before.sqlite3')
        accounts=workspace/'state/unified-server/accounts.sqlite3'
        if accounts.exists():backup(accounts,area/'accounts-before.sqlite3')
        for name in ('rates.json','events.json'):
            previous=workspace/'state/unified-server/gm'/name
            if previous.exists():
                plain_absolute(previous)
                kept=area/'private-settings-before'/name;kept.parent.mkdir(exist_ok=True);shutil.copy2(previous,kept)
        target=area/'runtime';target.mkdir()
        for row in rows:
            p=under(target,row['path']);p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/row['path'],p)
            assert sha(p)==row['sha256']
        provision(workspace,game,operation_token=identity['token'])
        # Candidate imports/checks only receive API snapshots, never player DBs.
        import tomllib
        from provision_unified_server import toml
        check=tomllib.loads((workspace/'state/unified-server/server.toml').read_text('utf8'))['server']
        for key,name in [('state_file','check-game.sqlite3'),('accounts_file','check-accounts.sqlite3')]:
            backup(Path(check[key]),area/name);check[key]=str(area/name)
        check['log_dir']=str(area/'check-logs');(area/'check.toml').write_text(toml(check),'utf8')
        q=subprocess.run([str(target/'python/python.exe'),'-B','-X','utf8','-m','els_server','--config',str(area/'check.toml'),'--check'],cwd=target,capture_output=True,timeout=120,creationflags=0x08000000)
        (area/'check.log').write_bytes(q.stdout+q.stderr);assert q.returncode==0,'Installed configuration/resource check failed; current retained'
        manifest=dict(release=rid,channel='local',unified_runtime=True,shared_runtime_identity=aggregate,
            source_content_identity=content_identity,
            source_online_release=definition.get('source_online_release'),files=rows,file_count=len(rows),
            scope='One authenticated server/runtime; deployment bind IP and private paths are configuration',player_database_restore=False)
        save(target/'local-business-manifest.json',manifest);save(target/'client-bundle-manifest.json',manifest)
        save(target/'release-snapshot.json',dict(release=rid,channel='local',unified_runtime=True,local_business_manifest_sha256=sha(target/'local-business-manifest.json')))
        current=dict(ok=True,release=rid,channel='local',path=destination.relative_to(workspace).as_posix(),unified_runtime=True,
            manifest_sha256=sha(target/'local-business-manifest.json'),runtime_manifest_sha256=sha(target/'client-bundle-manifest.json'),
            shared_runtime_identity=aggregate,source_online_release=definition.get('source_online_release'),server_host='127.0.0.1',
            source_content_identity=content_identity,
            config=str(workspace/'state/unified-server/server.toml'),parent_release=prior.get('release')if prior else None,
            backup=str(area),player_database_restore=False,old_runtime_cleanup_pending=bool(prior),normal_next_start=True)
        assert(pointer.read_bytes()if pointer.exists()else None)==prior_raw,'Parent changed before selection'
        if publication is not None:publication_locks(workspace,publication,delegation)
        transaction.update(phase='ready-to-select',candidate=current,manifest_sha256=current['manifest_sha256']);save(journal,transaction)
        destination.parent.mkdir(parents=True,exist_ok=True)
        os.rename(target,destination)
        save(pointer,current);save(area/'installation.json',current)
        transaction['phase']='selected';save(journal,transaction)
        return dict(ok=True,reused=False,release=rid,workspace=str(workspace),runtime=str(destination),backup=str(area))
    finally:
        try:
            stage=area/'runtime'
            if stage.exists():
                assert stage.resolve().parent==area.resolve()and stage.resolve().is_relative_to(workspace/'state/unified-installer')
                assert not stage.is_symlink()and not stage.is_junction()
                assert all(not p.is_symlink()and not p.is_junction()for p in stage.rglob('*'))
                shutil.rmtree(stage)
        finally:
            for p,inode in reversed(locks):
                assert p.stat().st_ino==inode and json.loads(p.read_bytes())==identity
                p.unlink()

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--result',type=Path,required=True);p.add_argument('--publication',type=Path)
    args=p.parse_args()
    try:result=install(args.workspace,json.loads(args.manifest.read_bytes()),args.publication)
    except BaseException as e:save(args.result,dict(ok=False,error=str(e),player_database_restore=False));raise
    save(args.result,result)
