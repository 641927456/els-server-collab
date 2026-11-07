"""Exercise the current launcher's real LOCAL selector without starting a game."""
from delivery_common import *
import os
P=W/'publication'
def locks():
 v=read(P/'reservation.json');assert v['identity']['thread']==OWNER
 for name,inode in v['inodes'].items():
  p=R/'analysis/coordination-20261015'/name;assert p.stat().st_ino==inode and read(p)==v['identity']
import subprocess
locks();launcher=read(R/'releases/launchers/current.json');assert sha(launcher['path'])==launcher['sha256']
assert read(R/'releases/local/current.json')['release']=='local-three-activities-startup-ui-20261101-v1'
source=r'''using System;
using System.IO;
using System.Reflection;
using System.Collections.Generic;
using System.Web.Script.Serialization;
class Check {
 static int Main(string[] args) {
  var a=Assembly.LoadFile(Path.GetFullPath(args[0]));var t=a.GetType("ElsFriends.LaunchMode",true);
  var flags=BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic;
  t.GetField("LocalRoot",flags).SetValue(null,args[1]);t.GetField("Local",flags).SetValue(null,true);
  string root=(string)t.GetMethod("Prepare",flags).Invoke(null,new object[]{new Action<string>(delegate(string ignored){})});
  if(!String.Equals(Path.GetFullPath(root),Path.GetFullPath(args[2]),StringComparison.OrdinalIgnoreCase))throw new Exception("Launcher selected another runtime");
  var identity=(Dictionary<string,object>)t.GetMethod("VerifiedLocalIdentity",flags).Invoke(null,new object[]{root});
  var result=new Dictionary<string,object>{{"ok",true},{"actual_launcher_selector",true},{"all_selected_components_verified",true},{"game_started",false},{"root",root},{"identity",identity}};
  File.WriteAllText(args[3],new JavaScriptSerializer().Serialize(result));return 0;
 }
}'''
cs=P/'launcher_local_verify.cs';cs.write_text(source,'utf8');exe=P/'launcher_local_verify.exe'
compiler=Path(os.environ['WINDIR'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
q=subprocess.run([str(compiler),'/nologo','/target:exe','/out:'+str(exe),'/reference:System.Web.Extensions.dll',str(cs)],capture_output=True,timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
assert q.returncode==0,q.stdout.decode('utf8','replace')
out=P/'launcher-local-verification.json'
q=subprocess.run([str(exe),launcher['path'],str(R),str(R/read(W/'raw-local-support/installation.json')['pointer']['path']),str(out)],capture_output=True,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
assert q.returncode==0,q.stderr.decode('utf8','replace')
assert read(out)['ok'];print(json.dumps(dict(ok=True,V=launcher['V'],selected_local_release='local-three-activities-startup-ui-20261101-v1',all_selected_components_verified=True,game_started=False)))
