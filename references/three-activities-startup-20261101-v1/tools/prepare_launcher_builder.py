from delivery_common import *
import ast
source=R/'analysis/distorted-memory-gate-20261101-v1/build_launcher_v60.py'
t=source.read_text('utf8')
original_ast=ast.dump(ast.parse(t))
t=''.join(' '*(4*(len(line)-len(line.lstrip(' '))))+line.lstrip(' ') for line in t.splitlines(True))
assert ast.dump(ast.parse(t))==original_ast
def one(a,b):
    global t
    assert t.count(a)==1,(a[:100],t.count(a));t=t.replace(a,b,1)
one("MANAGED='local-git-first-run-quest-gates-20261101-v1'","MANAGED='local-git-first-run-activities-startup-20261101-v1'")
one("DELTA={'els_server/domain/public_controller_rules.py','els_server/domain/story_controller_retirements.py','els_server/domain/friends_story_retirements.py'}",'''PROFILE='tools/client_compatibility_profiles.json'
ORIGINAL=R/'analysis/distorted-memory-gate-20261101-v1'
UI=R/'analysis/startup-ui-hide-20261101-v1'
DELTA=set(json.loads((W/'publication/release-contract.json').read_bytes())['local']['delta'][i]['path']for i in range(14))
DELTA|={r['path']for r in json.loads((R/'analysis/shop-rare-navy-20261101-v1/publication/release-contract.json').read_bytes())['local']['delta']}
DELTA|={'els_server/domain/public_controller_rules.py','els_server/domain/story_controller_retirements.py','els_server/domain/friends_story_retirements.py','els_server/domain/field_travel.py','els_server/protocol/field_boss_messages.py'}''')
one("    point=read(R/'releases/local/current.json');assert point['native_controller_quest_gates'];raw=R/point['path']","    contract=read(W/'publication/release-contract.json')['local'];point=read(R/'releases/local/current.json');assert point['release']==contract['parent']['release'];raw=R/contract['root']")
one("    assert point['release']=='local-elrian-breakable-gates-20261101-v1'","    assert read(W/'publication/local-install/qualification.json')['ok']\n    assert read(W/'startup-independent-review.json')['result']=='PASS'")
one("W/'git-source/tools/check_controller_quest_gates.py'","ORIGINAL/'git-source/tools/check_controller_quest_gates.py'")
one("W/'git-source/references/controller-quest-gates-20261101-v1/cases.json'","ORIGINAL/'git-source/references/controller-quest-gates-20261101-v1/cases.json'")
anchor="    for row in meta['support_overrides']:\n        if row['path']in DELTA:row['runtime_sha256']=sha(files[row['path']])\n    for row in meta['support_additions']:\n        if row['path']in DELTA:row['runtime_sha256']=sha(files[row['path']])"
one(anchor,'''    for row in read(UI/'update-delta-manifest.json')['modes']['local']['files']:
        data=(UI/'update-delta/local'/row['path']).read_bytes();assert sha(data)==row['sha256'];files[row['path']]=data
    profile=json.loads(files[PROFILE])
    for entry in profile['profiles']:
        for path in entry.get('artifacts',{}):assert path in files;entry['artifacts'][path]=sha(files[path])
    files[PROFILE]=enc(profile)
    formal_index={r['path']:r for r in formal}
    meta['support_overrides']=[dict(path=n,source_sha256=r['sha256'],runtime_sha256=sha(files[n]))for n,r in sorted(formal_index.items())if n!='config/server.toml'and sha(files[n])!=r['sha256']]
    additions={r['path']for r in oldmeta['support_additions']}|(set(files)-set(before))
    additions-=set(formal_index)|{'local-bootstrap-source.json'}
    meta['support_additions']=[dict(path=n,runtime_sha256=sha(files[n]))for n in sorted(additions)]''')
one("    assert {n for n in files if files[n]!=before[n]}==DELTA|{'local-bootstrap-source.json'}","    changed={n for n in files if files[n]!=before.get(n)}\n    assert changed==DELTA|{'local-bootstrap-source.json'}|{r['path']for r in read(UI/'update-delta-manifest.json')['modes']['local']['files']},changed\n    assert len(files)==1892")
anchor="    oldbuilder=load('builder59',P.parent/'build_launcher_v59.py')"
friends='''    friends_ref=old['signed_bindings']['signedFriends']
    feb=Path(friends_ref['manifest']['path']).read_bytes();assert sha(feb)==friends_ref['manifest']['sha256']
    fe=json.loads(feb);fpb=base64.b64decode(fe['payload'],validate=True);key.public_key().verify(base64.b64decode(fe['signature'],validate=True),fpb,padding.PKCS1v15(),hashes.SHA256());fd=json.loads(fpb)
    fa=Path(friends_ref['archive']['path']);assert sha(fa.read_bytes())==friends_ref['archive']['sha256']
    with zipfile.ZipFile(fa)as z:friends={n:z.read(n)for n in z.namelist()}
    assert file_rows(friends)==fd['files'];oldfriends=dict(friends)
    for row in read(UI/'update-delta-manifest.json')['modes']['friends']['files']:
        data=(UI/'update-delta/friends'/row['path']).read_bytes();assert sha(data)==row['sha256'];friends[row['path']]=data
    assert {n for n in friends if friends[n]!=oldfriends.get(n)}=={r['path']for r in read(UI/'update-delta-manifest.json')['modes']['friends']['files']}
    assert len(friends)==1800
    tmp=D/'signedFriends.zip'
    with zipfile.ZipFile(tmp,'x',zipfile.ZIP_DEFLATED,compresslevel=6)as z:
        for n,b in sorted(friends.items()):
            zi=zipfile.ZipInfo(n,(2026,11,1,0,0,0));zi.compress_type=zipfile.ZIP_DEFLATED;zi.external_attr=0o100644<<16;z.writestr(zi,b)
    ft=D/('runtime-'+sha(tmp.read_bytes())+'.zip');tmp.rename(ft)
    fd.update(archive=dict(file=ft.name,size=ft.stat().st_size,sha256=sha(ft.read_bytes())),files=file_rows(friends))
    fpb=json.dumps(fd,separators=(',',':')).encode();fsigned=json.dumps(dict(payload=base64.b64encode(fpb).decode(),signature=base64.b64encode(key.sign(fpb,padding.PKCS1v15(),hashes.SHA256())).decode()),separators=(',',':')).encode()
    fm=D/'signedFriends.signed.json';fm.write_bytes(fsigned);put('resources/quest-gates-signedFriends.signed.json',fsigned)
    friend_binding=dict(manifest=dict(path=str(fm),sha256=sha(fsigned)),archive=dict(path=str(ft),sha256=sha(ft.read_bytes())))
'''
one(anchor,friends+anchor)
one("values=dict(LocalPayload=binding['archive']['sha256'],LocalEnvelope=binding['manifest']['sha256'],LocalMetadata=sha(files['local-bootstrap-source.json']),BootstrapHash=sha(bootstrap.encode()))","values=dict(LocalPayload=binding['archive']['sha256'],LocalEnvelope=binding['manifest']['sha256'],LocalMetadata=sha(files['local-bootstrap-source.json']),BootstrapHash=sha(bootstrap.encode()),FriendsPayload=friend_binding['archive']['sha256'],FriendsEnvelope=friend_binding['manifest']['sha256'],FriendsProfileHash=sha(friends[PROFILE]))")
one("    put('QuestGatesRuntimeCohort.cs',cohort)","    cohort=cohort.replace('LocalCount=1887,FriendsCount=1798','LocalCount=1892,FriendsCount=1800').replace('ElsFriends.RegisteredGroundFriendsRuntimeFiles','ElsFriends.QuestGatesFriendsRuntimeFiles')\n    put('QuestGatesRuntimeCohort.cs',cohort)")
one("    put('ComponentRuntime.cs',t)","    start=t.index('        static RuntimeDefinition SelectRegisteredGroundFriendsDefinition()');end=t.index('        static RuntimeDefinition SelectShopFriendsDefinition()',start)\n    part=t[start:end].replace('RegisteredGroundRuntimeCohort.','QuestGatesRuntimeCohort.')\n    t=t[:start]+part+t[end:]\n    put('ComponentRuntime.cs',t)")
one("[('quest-gates-signedLOCAL.signed.json','QuestGatesLocalRuntimeFiles'),","[('quest-gates-signedFriends.signed.json','QuestGatesFriendsRuntimeFiles'),('quest-gates-signedLOCAL.signed.json','QuestGatesLocalRuntimeFiles'),")
one("signedFriends=old['signed_bindings']['signedFriends']","signedFriends=friend_binding")
one("component_delta=dict(signedLOCAL=sorted(DELTA|{'local-bootstrap-source.json'}),signedFriends=[])","component_delta=dict(signedLOCAL=sorted(changed),signedFriends=sorted(n for n in friends if friends[n]!=oldfriends.get(n)))")
one("new_Hooks=0","new_Hooks=1,independent_Hook_review=dict(path=str(W/'startup-independent-review.json'),sha256=sha((W/'startup-independent-review.json').read_bytes()))")
one("LOCAL_changed=4,Friends_changed=0","LOCAL_changed=len(changed),Friends_changed=4")
ast.parse(t);(W/'build_launcher_v60.py').write_text(t,'utf8')
print('Prepared a new V60 freeze builder; original V60 candidate remains unchanged')
