from delivery_common import *
import ast
t=(R/'analysis/distorted-memory-gate-20261101-v1/publish_launcher_v60.py').read_text('utf8')
def one(a,b):
 global t
 assert t.count(a)==1,(a[:90],t.count(a));t=t.replace(a,b,1)
t=t.replace("OWNER='01a19436-2d32-74c1-aae2-9422defc2d28'","OWNER='"+OWNER+"'")
t=t.replace('launcher-quest-gates-20261101-v60-v1','launcher-activities-startup-20261101-v60-v1').replace('quest-gates-v60-v1','activities-startup-v60-v1').replace("H=R/'analysis/qg60u'","H=R/'analysis/qa60u'")
one(" inputs={b['latest']['file']:Path(b['exe'])};a=Path(b['signed_bindings']['signedLOCAL']['archive']['path']);inputs[a.name]=a;pins={n:dict(size=p.stat().st_size,sha256=sha(p))for n,p in inputs.items()}"," inputs={b['latest']['file']:Path(b['exe'])}\n for family in ('signedLOCAL','signedFriends'):\n  a=Path(b['signed_bindings'][family]['archive']['path']);inputs[a.name]=a\n pins={n:dict(size=p.stat().st_size,sha256=sha(p))for n,p in inputs.items()}")
start=t.index(" oldhash={r['sha256']for r in definition(");end=t.index(" save(D/'index-additions.json'",start)
t=t[:start]+" old=read(OLD/'build.json');oldhash={r['sha256']for family in ('signedLOCAL','signedFriends')for r in definition(old,family)['files']};adds={}\n for family in ('signedLOCAL','signedFriends'):\n  d=definition(b,family)\n  for r in d['files']:\n   if r['sha256']not in oldhash:adds.setdefault(r['sha256'],dict(archive=d['archive']['file'],entry=r['path'],size=r['size']))\n assert len(adds)>4\n"+t[end:]
one("  assert t.count('==59,')==1;t=t.replace('==59,','=='+str(build['version'])+',')","  assert t.count('==59,')==1;t=t.replace('==59,','=='+str(build['version'])+',')\n  assert t.count('next?1887:')==1;t=t.replace('next?1887:','next?'+str(len(definition(build,'signedLOCAL')['files']))+':')")
one(" assert reports[1]['component_stats']['downloaded_files']==4 and reports[1]['component_stats']['reused_files']==1883\n assert reports[2]['component_stats']['downloaded_files']==0 and reports[2]['component_stats']['reused_files']==1887"," assert reports[1]['component_stats']['downloaded_files']==32 and reports[1]['component_stats']['reused_files']==1860\n assert reports[2]['component_stats']['downloaded_files']==0 and reports[2]['component_stats']['reused_files']==1892")
one("changed_downloads=4,reused=1883,repeat_downloads=0","changed_downloads=32,reused=1860,repeat_downloads=0")
# Add a normal-network Friends selector; preserve the reviewed offline seed.
marker=" save(P/'public-qualification.json',dict("
extra=''' template=(R/'analysis/pending-repairs-completion-20261031-v1/launcher-wear-v50-v2/friends_component_reader.cs').read_text('utf8')
 template=template.replace('if(mode=="good")throw','if(mode=="good"||mode=="public")throw').replace('if(mode!="good"){','if(mode!="good"&&mode!="public"){')
 anchor='c.GetField("TestTransport",flags).SetValue(null,transport);';assert template.count(anchor)==1;template=template.replace(anchor,'if(mode!="public")'+anchor)
 cs=D/'public-friends-reader.cs';cs.write_text(template,'utf8');reader=cs.with_suffix('.exe');run([compiler,'/nologo','/target:exe','/out:'+str(reader),'/reference:System.Web.Extensions.dll','/reference:System.IO.Compression.dll','/reference:System.IO.Compression.FileSystem.dll',cs],'public-friends-compile')
 freports=[]
 for label,build,mode in [('old59-friends-seed',read(OLD/'build.json'),'good'),('public60-friends',b,'public')]:
  out=H/(label+'.json');run([reader,build['exe'],H/'f',build['signed_bindings']['signedFriends']['archive']['path'],out,mode],label,timeout=240);result=read(out);assert result['ok']and result['selected_identity']['payload']==build['signed_bindings']['signedFriends']['archive']['sha256']and result['second']['downloaded_files']==0;freports.append(result)
 assert freports[1]['first']['downloaded_files']==4 and freports[1]['first']['reused_files']==1796
 save(P/'public-friends-qualification.json',dict(ok=True,actual_default_CSharp_selector=True,pinned_TLS_and_signatures=True,changed_downloads=4,reused=1796,repeat_downloads=0,reports=freports,game_started=False))
'''
one(marker,extra+marker)
one("public_V59_to_V60_EXE_download_verified=True,quest_gate_signed_LOCAL=True","public_V59_to_V60_EXE_download_verified=True,runtime_manifest=b['signed_bindings']['signedFriends']['manifest']['path'],payload_sha256=b['signed_bindings']['signedFriends']['archive']['sha256'],payload_files_verified=1800,actual_payload_ZIP_members=1800,runtime_components_verified=1800,local_runtime_files=1892,UI_support_signed_both=True,Boost_LOCAL_signed=True,shop_rare_navy_signed_LOCAL=True,quest_gate_signed_LOCAL=True")
t=t.replace('public_signed_LOCAL_delta=4','public_signed_LOCAL_delta=32,public_signed_Friends_delta=4').replace('Friends_payload_unchanged=True','Friends_UI_only_delta=True').replace('existing_LOCAL_upgrade_Run=False','existing_LOCAL_upgrade_Run=True').replace('existing_upgrade_pending_normal_game_exit=True','existing_upgrade_pending_normal_game_exit=False').replace('fresh_LOCAL_Run_verified=True','fresh_LOCAL_Run_verified=False,fresh_install_mechanism_reused=True')
one("if __name__=='__main__':",'''def adopt():
 assert not(P/'reservation.json').exists()
 h=read(W/'publication/reservation.json');assert h['identity']['thread']==OWNER
 for n,ino in h['inodes'].items():
  f=R/'analysis/coordination-20261015'/n;assert f.stat().st_ino==ino and read(f)==h['identity']
 assert read(R/'releases/online/current.json')['release']=='three-activities-integrated-20261101-v1'
 assert read(R/'releases/local/current.json')['release']=='local-three-activities-integrated-20261101-v1'
 b=read(D/'build.json');assert read(R/'releases/launchers/current.json')==b['parent']
 assert read(W/'public-ui-trial-2/result.json')['ok']
 save(P/'reservation.json',dict(identity=h['identity'],inodes=h['inodes'],runtime_pins={str(R/'releases'/c/'current.json'):sha(R/'releases'/c/'current.json')for c in ('online','local')},launcher_parent={n:dict(path=str(R/'releases/launchers'/n),sha256=sha(R/'releases/launchers'/n))for n in ('current.json','standalone-current.json')}))
 pre();print('Existing own publication lease adopted; server unchanged',flush=True)
if __name__=='__main__':''')
one("choices=['reserve','stage','qualify_public','promote']","choices=['adopt','stage','qualify_public','promote']")
ast.parse(t);(W/'publish_launcher_v60.py').write_text(t,'utf8')
print('Prepared signed dual-mode publication using the existing own lease')
