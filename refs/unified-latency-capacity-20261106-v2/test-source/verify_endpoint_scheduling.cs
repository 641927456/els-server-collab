using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Web.Script.Serialization;
class OwnedEndpointPreview {
 static int Main(string[] args) {
  Process.GetCurrentProcess().PriorityClass=ProcessPriorityClass.BelowNormal;
  var json=new JavaScriptSerializer();var assembly=Assembly.LoadFile(Path.GetFullPath(args[0]));
  var program=assembly.GetType("ElsFriends.Program",true);var mode=assembly.GetType("ElsFriends.LaunchMode",true);var endpoint=assembly.GetType("ElsFriends.UnifiedEndpoint",true);
  program.GetField("DataRoot").SetValue(null,Path.Combine(args[1],"state","owned-launcher"));
  mode.GetField("Local").SetValue(null,true);mode.GetField("LocalRoot").SetValue(null,Path.GetFullPath(args[1]));
  Process child=null;int pid=0;string executable=null;bool stopped=false;
  try {
   endpoint.GetMethod("EnsureRunning").Invoke(null,null);
   var owned=(Process)endpoint.GetField("owned",BindingFlags.Static|BindingFlags.NonPublic).GetValue(null);
   pid=owned.Id;child=Process.GetProcessById(pid);var retainedHandle=child.Handle;executable=child.MainModule.FileName;
   if(!executable.EndsWith("\\server-python\\python.exe",StringComparison.OrdinalIgnoreCase))throw new Exception("Wrong server interpreter selected");
   if(child.PriorityClass!=ProcessPriorityClass.Normal)throw new Exception("Game child inherited background CPU priority");
   endpoint.GetMethod("EnsureRunning").Invoke(null,null);
   var same=(Process)endpoint.GetField("owned",BindingFlags.Static|BindingFlags.NonPublic).GetValue(null);
   if(same.Id!=pid)throw new Exception("Repeat created another server");
  } finally {
   endpoint.GetMethod("StopOwnedForUpdate").Invoke(null,null);
   if(child!=null){if(!child.WaitForExit(30000)||child.ExitCode!=0)throw new Exception("Owned server did not exit normally");stopped=true;child.Dispose();}
  }
  File.WriteAllText(args[2],json.Serialize(new {passed=true,actual_compiled_endpoint=true,child_pid=pid,actual_server_interpreter=executable,repeat_reuses_same_server=true,normal_stop=stopped,physical_player_input=false,production_installed=false,parent_CPU_below_normal=true,actual_game_CPU_priority=32}));return 0;
 }
}
