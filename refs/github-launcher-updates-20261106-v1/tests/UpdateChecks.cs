using System;using System.IO;using System.Linq;using System.Reflection;using System.Collections.Generic;using System.Web.Script.Serialization;
class UpdateChecks {
 static BindingFlags Flags=BindingFlags.Static|BindingFlags.Public|BindingFlags.NonPublic;
 static object Invoke(Type t,string method,params object[] args){return t.GetMethod(method,Flags).Invoke(null,args);}
 static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
 static int Main(string[] a){try{
  var asm=Assembly.LoadFile(Path.GetFullPath(a[0]));string mode=a[1];var update=asm.GetType("ElsFriends.AutoUpdate");
  if(mode=="policy") {
   var transport=asm.GetType("ElsFriends.GitHubUpdates");
   foreach(string asset in new[]{"latest.json","v83-0123456789abcdef.exe","runtime-"+new string('a',64)+".zip","chunk-"+new string('b',64)+".zip"})Need((bool)Invoke(transport,"Allowed",new Uri((string)Invoke(transport,"Address",asset,new string('a',64)))),"Valid asset rejected");
   foreach(string bad in new[]{"../latest.json","v83-0123456789abcdef.exe?x=1","runtime-a.zip","https://evil.test/a","blob-"+new string('a',64)+".bin"}){bool rejected=false;try{Invoke(transport,"Address",bad,null);}catch(TargetInvocationException){rejected=true;}Need(rejected,"Unsafe asset accepted");}
   foreach(string bad in new[]{"http://github.com/641927456/els-launcher-updates/releases/latest/download/latest.json","https://github.com:444/641927456/els-launcher-updates/releases/a","https://evil.test/a","https://github.com.evil.test/a","https://release-assets.githubusercontent.com.evil.test/a","https://user@github.com/641927456/els-launcher-updates/releases/a","https://github.com/other/repo/releases/a","https://github.com/641927456/els-launcher-updates/releases/a#b","https://github.com/641927456/els-launcher-updates/releases/a?b"})Need(!(bool)Invoke(transport,"Allowed",new Uri(bad)),"Unsafe redirect accepted");
   foreach(string good in new[]{"https://release-assets.githubusercontent.com/github-production-release-asset/a?token=fixture","https://objects.githubusercontent.com/github-production-release-asset/a"})Need((bool)Invoke(transport,"Allowed",new Uri(good)),"CDN rejected");
   foreach(string name in new[]{"tampered","wrong-key","bad-path","wrong-channel","oversize"}){bool rejected=false;try{Invoke(update,"Verify",File.ReadAllText(Path.Combine(a[2],name+".json")));}catch(TargetInvocationException){rejected=true;}Need(rejected,"Unsafe signed metadata accepted: "+name);}
   Invoke(update,"Verify",File.ReadAllText(Path.Combine(a[2],"valid.json")));
   var components=asm.GetType("ElsFriends.ComponentRuntime");
   foreach(string name in new[]{"duplicate-member","missing-member","bad-chunk-path","wrong-chunk-hash","tampered-runtime"}){bool rejected=false;try{Invoke(components,"Verify",File.ReadAllText(Path.Combine(a[2],name+".json")));}catch(TargetInvocationException){rejected=true;}Need(rejected,"Unsafe chunk manifest accepted: "+name);}
   File.WriteAllText(a[3],"{\"ok\":true,\"redirect_policy\":true,\"release_signatures\":true,\"chunk_index_rejections\":true}");return 0;
  }
  string cache=Path.GetFullPath(a[2]);asm.GetType("ElsFriends.Program").GetField("DataRoot",Flags).SetValue(null,cache);
  if(mode=="asset") {
   var release=Invoke(update,"Verify",File.ReadAllText(a[3]));var rt=release.GetType();Directory.CreateDirectory(cache);string path=Path.Combine(cache,(string)rt.GetField("FileName").GetValue(release));
   var transport=asm.GetType("ElsFriends.GitHubUpdates");
   using(var response=(System.Net.HttpWebResponse)Invoke(transport,"Open",Path.GetFileName(path),null))using(var input=response.GetResponseStream())using(var output=File.Create(path))input.CopyTo(output);
   Need((bool)Invoke(update,"ValidFile",path,release),"Public EXE differs");
   File.WriteAllText(a[4],new JavaScriptSerializer().Serialize(new{ok=true,path=path,anonymous=true,signature_verified=true,sha256_verified=true,game_started=false}));return 0;
  }
  if(mode=="download") {
   var release=Invoke(update,"Verify",File.ReadAllText(a[3]));string path=(string)Invoke(update,"Download",release,new Action<int>(n=>{}));Need(path!=null&&(bool)Invoke(update,"ValidFile",path,release),"Invalid public update");File.WriteAllText(a[4],new JavaScriptSerializer().Serialize(new{ok=true,path=path,anonymous=true,game_started=false}));return 0;
  }
  if(mode=="latest") {var release=Invoke(update,"Latest");File.WriteAllText(a[3],new JavaScriptSerializer().Serialize(new{ok=true,version=release.GetType().GetField("Version").GetValue(release)}));return 0;}
  var c=asm.GetType("ElsFriends.ComponentRuntime");int requests=0;long transferred=0;var names=new List<string>();string pointer=Path.Combine(cache,"component-state","current.json");string before=File.Exists(pointer)?File.ReadAllText(pointer):null;
  if(mode!="public"&&mode!="publicfresh") {
   Func<string,Stream> test=name=>{requests++;names.Add(name);string path=Path.Combine(a[3],name);if(!File.Exists(path))throw new IOException("Unexpected local asset: "+name);byte[] raw=File.ReadAllBytes(path);transferred+=raw.Length;if(mode=="corrupt")raw[raw.Length-1]^=1;if(mode=="truncated")raw=raw.Take(raw.Length-1).ToArray();return new MemoryStream(raw,false);};
   c.GetField("TestTransport",Flags).SetValue(null,test);
  }
  bool runtimeRejected=false;string root=null;
  try{root=(string)Invoke(c,"Ensure",new Action<string>(s=>{}));}catch(TargetInvocationException){if(mode!="corrupt"&&mode!="truncated")throw;runtimeRejected=true;}
  if(mode=="corrupt"||mode=="truncated") {
   Need(runtimeRejected&&requests>0,"Broken asset accepted");Need((File.Exists(pointer)?File.ReadAllText(pointer):null)==before,"Failure changed prior pointer");Need(Directory.GetDirectories(Path.Combine(cache,"component-runtimes"),"prepare-*").Length==0,"Failed stage leaked");
   File.WriteAllText(a[4],new JavaScriptSerializer().Serialize(new{ok=true,rejected=true,prior_pointer_preserved=true,requests=requests,mode=mode}));return 0;
  }
  var first=c.GetField("LastResult",Flags).GetValue(null);int initial=requests;Need(root==(string)Invoke(c,"Ensure",new Action<string>(s=>{}))&&requests==initial,"Complete cache downloaded again");
  File.WriteAllText(a[4],new JavaScriptSerializer().Serialize(new{ok=true,root=root,first=first,second=c.GetField("LastResult",Flags).GetValue(null),requests=requests,assets=names.ToArray(),bytes=transferred,identity=Invoke(c,"VerifiedPreparedIdentity",root),game_started=false,network=mode=="public"||mode=="publicfresh"}));return 0;
 }catch(Exception e){Console.Error.WriteLine(e);return 1;}}
}
