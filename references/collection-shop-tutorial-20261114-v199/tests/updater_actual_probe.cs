using System;using System.IO;using System.Reflection;using System.Collections.Generic;using System.Web.Script.Serialization;
class UpdaterActualProbe {
 static readonly BindingFlags F=BindingFlags.Public|BindingFlags.NonPublic|BindingFlags.Static;
 static object Call(Type type,string name,params object[] args){return type.GetMethod(name,F).Invoke(null,args);}
 [STAThread]static int Main(string[] a){var result=new Dictionary<string,object>();try{
  AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling",false);AppContext.SetSwitch("Switch.System.IO.BlockLongPaths",false);
  var assembly=Assembly.LoadFile(Path.GetFullPath(a[0]));var storage=assembly.GetType("ElsFriends.ClientStorage");
  Call(storage,"SelectProfile",Path.GetFullPath(a[2]));Call(storage,"Activate",Path.GetFullPath(a[3]));
  var updater=assembly.GetType("ElsFriends.AutoUpdate");object release=Call(updater,"Verify",File.ReadAllText(a[1]));
  string path=(string)Call(updater,"Download",release,new Action<int>(delegate{}));
  if(path==null||!(bool)Call(updater,"ValidFile",path,release))throw new Exception("Old actual updater did not produce a verified newer launcher");
  result["ok"]=true;result["anonymous"]=true;result["path"]=path;result["game_started"]=false;
 }catch(Exception error){result["ok"]=false;result["error"]=error.ToString();}
 File.WriteAllText(a[4],new JavaScriptSerializer{MaxJsonLength=1024*1024}.Serialize(result));return(bool)result["ok"]?0:1;
 }
}
