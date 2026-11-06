from delivery_common import *
import ast
source=R/'analysis/distorted-memory-gate-20261101-v1/qualify_launcher_v60.py';t=source.read_text('utf8')
before=ast.dump(ast.parse(t));t=''.join(' '*(4*(len(x)-len(x.lstrip(' '))))+x.lstrip(' ')for x in t.splitlines(True));assert ast.dump(ast.parse(t))==before
def one(a,b):
    global t
    assert t.count(a)==1,(a[:100],t.count(a));t=t.replace(a,b,1)
one("H=R/'analysis/qg60'","H=R/'analysis/qa60a'")
t=t.replace("'01a19436-2d32-74c1-aae2-9422defc2d28'",repr(OWNER))
one("W/'git-source',repo","R/'analysis/shop-rare-navy-20261101-v1/git-source',repo")
t=t.replace("W/'git-source/tools/check_controller_quest_gates.py'","R/'analysis/distorted-memory-gate-20261101-v1/git-source/tools/check_controller_quest_gates.py'")
t=t.replace("W/'git-source/references/controller-quest-gates-20261101-v1/cases.json'","R/'analysis/distorted-memory-gate-20261101-v1/git-source/references/controller-quest-gates-20261101-v1/cases.json'")
marker="    save(D/'qualification.json',dict("
extra='''    friend_template=R/'analysis/pending-repairs-completion-20261031-v1/launcher-wear-v50-v2/friends_component_reader.cs'
    assert sha(friend_template)=='52e8fecb39cbe6ce5df642a896a8e7b87daf5c1a2a20244e5da092041bc0e086'
    cs=D/'friends-reader.cs';cs.write_bytes(friend_template.read_bytes());reader=cs.with_suffix('.exe')
    run([compiler,'/nologo','/target:exe','/out:'+str(reader),'/reference:System.Web.Extensions.dll','/reference:System.IO.Compression.dll','/reference:System.IO.Compression.FileSystem.dll',cs],'friends-reader-compile')
    friends_reports=[]
    for label,build in [('old59-friends',old),('new60-friends',b)]:
        output=H/(label+'.json');run([reader,build['exe'],H/'f',build['signed_bindings']['signedFriends']['archive']['path'],output,'good'],label,timeout=240)
        item=read(output);assert item['ok']and item['selected_identity']['payload']==build['signed_bindings']['signedFriends']['archive']['sha256']and item['second']['downloaded_files']==0;friends_reports.append(item)
    friend_root=Path(friends_reports[-1]['root']);newf=json.loads(base64.b64decode(read(b['signed_bindings']['signedFriends']['manifest']['path'])['payload']))
    for row in newf['files']:assert (friend_root/row['path']).stat().st_size==row['size']and sha(friend_root/row['path'])==row['sha256'],row['path']
    credentials=read(W/'qa-credentials.private.json');bridge_config=H/'bridge.private.json';save(bridge_config,credentials['bridge'])
    for family,selected_root in [('signedLOCAL',root),('signedFriends',friend_root)]:
        out=H/(family+'-compose.json')
        run([selected_root/'python/python.exe','-B','-X','utf8',P.parent/'qualify_launcher_v59.py','--child','compose',selected_root,db,out],family+'-compose',selected_root,240)
        composed=out.with_suffix('.js').read_text('utf8');assert 'installElsStartupVisibility();'in composed and '__STARTUP_UI_PINS__'not in composed
        # The formal client entry validates the complete selected profile/resource closure.
        run([selected_root/'python/python.exe','-B',selected_root/'tools/launch_friends_client.py','--config',bridge_config,'--client','D:/艾尔之光/data/x2_dx11.exe','--check'],family+'-formal-friends-entry-check',selected_root,240)
    save(D/'selected-support.json',dict(ok=True,LOCAL=str(root),Friends=str(friend_root),Friends_reports=friends_reports,selected_friends_files=len(newf['files']),formal_launch_friends_check_both=True,composed_startup_hook_both=True,game_started=False))
'''
one(marker,extra+marker)
one('all_1887_selected_files_verified=True','all_1892_selected_files_verified=True')
one('Friends_payload_unchanged=True','Friends_UI_only_delta=True,Friends_files=1800,LOCAL_files=1892,formal_friends_entry_check_both=True')
ast.parse(t);(W/'qualify_launcher_v60.py').write_text(t,'utf8')
print('Prepared real CSharp upgrade/repeat and both formal selected support checks')
