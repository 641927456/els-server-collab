from delivery_common import *
import ast,re,shutil
A=R/'analysis/labyrinth-mechanisms-delivery-20261101-v1'
t=(A/'launcher_publication_v61.py').read_text('utf8')
t=t.replace("OWNER='01a188cb-21df-7000-a927-f8dbad7e074d'","OWNER='"+OWNER+"'")
t=t.replace('launcher-labyrinth-mechanisms-20261101-v61-v1','launcher-ring-wear-20261101-v62-v1').replace('labyrinth-mechanisms-v61-v1','ring-wear-v62-v1').replace("H=R/'analysis/mp61p'","H=R/'analysis/ring62p'")
# Version-specific tokens must advance once, without transitive replacement.
for a,b in [('V60','__OLD_V__'),('V61','V62'),('__OLD_V__','V61'),('old60','__old__'),('download61','download62'),('public61','public62'),('__old__','old61'),('latest61','latest62')]:t=t.replace(a,b)
t=t.replace("['version']==60","['version']==61").replace("['version']==61 and", "['version']==62 and")
t=t.replace("b['version']==61","b['version']==62").replace("parent['V']==60","parent['V']==61")
t=t.replace('version!=61','version!=62').replace('old_version=60','old_version=61')
t=t.replace('V=61','V=62').replace("['V']==61","['V']==62")
# Restore the one actual-parent assertion after advancing current-output assertions.
t=t.replace("parent['V']==62","parent['V']==61")
t=t.replace("remote_parent['version']==62","remote_parent['version']==61")
t=t.replace('public_old61_downloaded_verified61=True','public_old61_downloaded_verified62=True')
def function(name,body):
 global t
 pattern=r'^def '+name+r'\(\):\n.*?(?=^def |^if __name__)'
 t,n=re.subn(pattern,lambda m:body.strip()+'\n\n\n',t,flags=re.M|re.S);assert n==1,name
function('preconditions',r'''
def preconditions():
    held();assert sha(ARGS.build)==ARGS.build_sha
    b=read(ARGS.build);assert b['ok']and b['version']==62 and sha(b['exe'])==b['exe_sha256']
    assert sha(ARGS.qualification)==ARGS.qualification_sha
    q=read(ARGS.qualification);assert q['ok']and q['exe_sha256']==b['exe_sha256']and q['build_sha256']==ARGS.build_sha
    for name in ('actual_CSharp_LOCAL_Run','upgrade61_to62','repeat','all_1892_selected_files_verified','typed_owned_databases_preserved','complete_new_three_position_readers_retained_in_guarded_tree','recovery_original_restore_disallowed','Friends_payload_unchanged','Friends_default_selector_current','Friends_repeat_zero_downloads'):assert q[name]is True,name
    assert q['predecessor_contracts']==18 and q['new_Hooks']==0
    assert expected_delta(b,'signedLOCAL')==(3,1889)and expected_delta(b,'signedFriends')==(0,1800)
    parent=read(R/'releases/launchers/current.json');assert parent==b['parent']and parent['V']==61
    assert read(R/'releases/launchers/standalone-current.json')['sha256']==parent['sha256']
    assert read(PARENT_BUILD)['exe_sha256']==parent['sha256']and sha(parent['path'])==parent['sha256']
    for ref in held()['launcher_parent_pins']:assert sha(ref['path'])==ref['sha256']
    for binding in b['signed_bindings'].values():
        for ref in binding.values():assert sha(ref['path'])==ref['sha256']
    return b
''')
function('adopt',r'''
def adopt():
    assert not(P/'reservation.json').exists()
    source=W/'publication/reservation.json';shared=read(source)
    assert shared['identity']['thread']==OWNER and shared['identity']['release']=='ring-wear-cross-bag-20261101-v1'
    assert set(shared['inodes'])=={'active-publication.lock','publication-record.lock'}
    for name,inode in shared['inodes'].items():
        p=R/'analysis/coordination-20261015'/name;assert p.stat().st_ino==inode and read(p)==shared['identity']
    b=read(ARGS.build);point=read(R/'releases/local/current.json');assert point['release']==b['raw_local_source']['release']and point['manifest_sha256']==b['raw_local_source']['manifest_sha256']
    paths=[R/'releases/online/current.json',R/'releases/local/current.json']
    pins=[dict(path=str(p),sha256=sha(p))for p in paths]
    launcher_pins=[dict(path=str(R/'releases/launchers'/n),sha256=sha(R/'releases/launchers'/n))for n in ('current.json','standalone-current.json')]
    save(P/'reservation.json',dict(identity=shared['identity'],inodes=shared['inodes'],shared_reservation=dict(path=str(source),sha256=sha(source)),runtime_pins=pins,launcher_parent_pins=launcher_pins,phase='launcher62-after-dual-installed',owns_lock_release=False))
    preconditions();print(json.dumps(dict(ok=True,shared_reservation_adopted=True,no_new_locks=True)))
''')
function('qualify_public',r'''
def qualify_public():
    b=preconditions();assert not H.exists();H.mkdir()
    save(H/'owner.json',dict(thread=OWNER,purpose='Public LOCAL ring delta selector; no game'))
    q=read(ARGS.qualification)
    save(D/'public-component-qualification.json',dict(ok=True,exe_sha256=b['exe_sha256'],Friends_bytes_exactly_V61=True,Friends_retested=False,reused_current_offline_friends_qualification=dict(path=str(ARGS.qualification),sha256=sha(ARGS.qualification)),game_started=False))
''')
# The reusable public selector is unchanged; counts and candidate version are inputs.
t=t.replace("b['actual_signed_LOCAL_count']","len(definition_rows(b,'signedLOCAL'))").replace("b['actual_signed_Friends_count']","len(definition_rows(b,'signedFriends'))")
t=t.replace('labyrinth_configuration_signed_synchronization=True','ring_wear_readers_signed_synchronization=True')
t=t.replace("source_contract=b['channel_contract']['path']","source_contract=str(W/'publication/release-contract.json')")
t=t.replace("'Related labyrinth source acceptance reused; new selected JSON verified; no natural GUI or new Hook claim'","'Public five-ring purchase, bidirectional replacement, cold restore and original native decoder verified; no natural GUI claim'")
# Do not mutate producer's special cleanup boundary. Our closeout is handled by this delivery.
function('closeout',r'''
def closeout():
    held();assert read(P/'installation.json')['ok']and read(P/'installation.json')['observation_seconds']>=120
    assert read(P/'launcher-stage-cleanup.json')['ok']
    save(P/'closeout.json',dict(ok=True,own_locks_released=False,shared_reservation_retained=True,public_cache_retained_for_exact_owner_cleanup=True,service_changes=0,public_accounts_created=0))
''')
needle="contract=read(read(ARGS.build)['channel_contract']['path']);PARENT_BUILD=Path(contract['parent_build']['path']);assert sha(PARENT_BUILD)==contract['parent_build']['sha256']"
assert t.count(needle)==1;t=t.replace(needle,"PARENT_BUILD=Path(read(W/'preceding-publisher-handoff.json')['parent_launcher_build'])")
t='\n'.join(line.rstrip()for line in t.splitlines())+'\n'
ast.parse(t);(W/'launcher_publication_v62.py').write_text(t,'utf8')
shutil.copy2(A/'launcher_owned_process.py',W/'launcher_owned_process.py')
print('Prepared owned V62 publisher; actual parent61, two runtime readers plus metadata only')
