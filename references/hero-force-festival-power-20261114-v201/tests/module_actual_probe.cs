using System;
using System.IO;
using System.Reflection;
using System.Collections;
using System.Collections.Generic;
using System.Text;
using System.Web.Script.Serialization;

class ModuleActualProbe {
 static readonly BindingFlags F=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Static;
 static Type component,lean;
 static object Call(Type type,string method,params object[] args){return type.GetMethod(method,F).Invoke(null,args);}
 static object Property(Type type,string name){return type.GetProperty(name,F).GetValue(null,null);}
 static int Files(string root,object definition){return ((ICollection)Call(component,"FilesAt",root,definition)).Count;}
 [STAThread] static int Main(string[] a) {
  var report=new Dictionary<string,object>();var requests=new List<string>();
  try {
   AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling",false);AppContext.SetSwitch("Switch.System.IO.BlockLongPaths",false);
   var assembly=Assembly.LoadFile(Path.GetFullPath(a[0]));
   var program=assembly.GetType("ElsFriends.Program");Call(program,"EnableLongPaths");
   var storage=assembly.GetType("ElsFriends.ClientStorage");Call(storage,"SelectProfile",Path.GetFullPath(a[2]));Call(storage,"Activate",Path.GetFullPath(a[3]));
   component=assembly.GetType("ElsFriends.ComponentRuntime");lean=assembly.GetType("ElsFriends.LeanRuntime");
   if(a[4]!="-")component.GetField("TestTransport",F).SetValue(null,new Func<string,Stream>(delegate(string name){requests.Add(name);return File.OpenRead(Path.Combine(a[4],name));}));
   var names=assembly.GetManifestResourceNames();if(names.Length!=6)throw new Exception("Unexpected embedded resource count");
   Call(assembly.GetType("ElsFriends.AutoUpdate"),"Verify",File.ReadAllText(Path.Combine(Path.GetDirectoryName(Path.GetFullPath(a[0])),"latest.json"),Encoding.UTF8));
   if(a[1]=="cache") {
    report["available_before"]=Call(component,"Available");
    if(report["available_before"]!=null)throw new Exception("Old directory was declared current before preparation");
   }
   string client=(string)Call(component,"Ensure",new Action<string>(delegate{}));
   report["client_root"]=client;report["client_files"]=Files(client,Property(lean,"Client"));report["client_first_stats"]=component.GetField("LastResult",F).GetValue(null);
   Call(component,"Ensure",new Action<string>(delegate{}));report["client_repeat_stats"]=component.GetField("LastResult",F).GetValue(null);
   report["prepared_identity"]=Call(component,"VerifiedPreparedIdentity",client);
   if(a[1]!="client"&&a[1]!="cache") {
    var modules=(Tuple<string,string>)Call(component,"EnsureLocalModules",new Action<string>(delegate{}));
    report["server_root"]=modules.Item2;report["server_files"]=Files(modules.Item2,Property(lean,"Server"));report["server_first_stats"]=component.GetField("LastResult",F).GetValue(null);
    Call(component,"EnsureLocalModules",new Action<string>(delegate{}));report["server_repeat_stats"]=component.GetField("LastResult",F).GetValue(null);
    string manifest=(string)Call(lean,"LocalManifest",modules.Item1,modules.Item2);report["local_manifest"]=new JavaScriptSerializer{MaxJsonLength=4*1024*1024}.DeserializeObject(manifest);
    if(a[1]=="install") {
     string workspace=Path.GetFullPath(a[6]);
     Call(assembly.GetType("ElsFriends.UnifiedInstall"),"RunPrepared",workspace,modules,new Action<int,string>(delegate{}));
     if(!(bool)Call(assembly.GetType("ElsFriends.LocalBootstrap"),"Current",workspace))throw new Exception("Installed local runtime is not the compiled signed composition");
     report["workspace"]=workspace;report["actual_installer"]=true;
    }
   }
   report["ok"]=true;report["network"]=a[4]=="-";report["embedded_resources"]=names;report["local_test_transport_requests"]=requests;report["game_started"]=false;
  }catch(Exception error){report["ok"]=false;report["error"]=error.ToString();}
  string json=new JavaScriptSerializer{MaxJsonLength=16*1024*1024}.Serialize(report);
  File.WriteAllText(a[5],json,new UTF8Encoding(false));Console.WriteLine((bool)report["ok"]?"Actual signed module probe passed":"Actual signed module probe failed; see owned report");
  return (bool)report["ok"]?0:1;
 }
}
