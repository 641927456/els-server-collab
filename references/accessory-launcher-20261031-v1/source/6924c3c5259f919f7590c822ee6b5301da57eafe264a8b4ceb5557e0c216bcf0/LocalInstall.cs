using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;

namespace ElsFriends {
    static class LocalInstall {
        internal const string RepairRawUpdaterHash="9b49b080cbd9728ed6049f3197c69fa16af66b6fd605899fb5ee6d71f73db0f3";
        static Dictionary<string,object> RecoveryDoc(string path) {
            RecoveryNoLinks(path);
            if(new FileInfo(path).Length>4*1024*1024)throw new IOException("Oversized raw recovery identity");
            return new System.Web.Script.Serialization.JavaScriptSerializer {MaxJsonLength=4*1024*1024,RecursionLimit=64}.Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));
        }
        static void RecoveryNoLinks(string path) {
            for(string p=Path.GetFullPath(path);!String.IsNullOrEmpty(p);p=Path.GetDirectoryName(p))
                if((File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0)throw new IOException("Linked raw recovery path");
        }
        static string RecoveryUnder(string root,string relative) {
            if(String.IsNullOrEmpty(relative)||Path.IsPathRooted(relative)||relative.IndexOf(':')>=0||relative.IndexOf('\\')>=0)throw new IOException("Invalid raw recovery relative path");
            foreach(string part in relative.Split('/'))if(part==".."||part=="."||part.Length==0)throw new IOException("Invalid raw recovery path segment");
            string p=Path.GetFullPath(Path.Combine(root,relative.Replace('/',Path.DirectorySeparatorChar)));
            if(!p.StartsWith(Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Raw recovery path escaped");
            RecoveryNoLinks(p);return p;
        }
        static bool RecoveryEqual(object a,object b) {
            var x=a as Dictionary<string,object>;var y=b as Dictionary<string,object>;
            if(x!=null||y!=null){if(x==null||y==null||x.Count!=y.Count)return false;foreach(var p in x){object v;if(!y.TryGetValue(p.Key,out v)||!RecoveryEqual(p.Value,v))return false;}return true;}
            var ax=a as System.Collections.IList;var bx=b as System.Collections.IList;
            if(ax!=null||bx!=null){if(ax==null||bx==null||ax.Count!=bx.Count)return false;for(int i=0;i<ax.Count;i++)if(!RecoveryEqual(ax[i],bx[i]))return false;return true;}
            return Object.Equals(a,b);
        }
        static string RecoveryHash(string path){using(var input=File.OpenRead(path))return Program.Hash(input);}
        // Select a retained interpreter only for this exact interrupted transaction.
        // This never admits normal startup; the embedded updater rechecks identity,
        // dead owner birth, source Git/profile, locks and all files before recovery.
        static string AccessoryRawRecoveryRoot(string workspace,string repository,string commit) {
            string root=Path.GetFullPath(workspace),ownerRoot=Path.Combine(root,"analysis","coordination-20261015");
            Dictionary<string,object> identity=null;
            foreach(string name in new[]{"active-publication.lock","publication-record.lock"}) {
                string file=Path.Combine(ownerRoot,name);if(!File.Exists(file))continue;
                var item=RecoveryDoc(file);if(identity!=null&&!RecoveryEqual(identity,item))throw new IOException("Raw recovery locks disagree");identity=item;
            }
            if(identity==null)return null;
            if(Convert.ToString(identity["schema"])!="els-local-oneclick-v1"||Convert.ToString(identity["operation"])!="local-oneclick-updater")throw new IOException("Foreign raw recovery owner");
            string path=Convert.ToString(identity["journal"]),journal=Path.GetFullPath(path);
            if(!Path.IsPathRooted(path)||!String.Equals(path,journal,StringComparison.OrdinalIgnoreCase)||Path.GetFileName(journal)!="journal.json"||!journal.StartsWith(Path.Combine(root,"state","local-updater")+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Invalid raw recovery journal location");
            var j=RecoveryDoc(journal);
            if(Convert.ToInt32(j["nine_recovery_schema"])!=1||Convert.ToString(j["schema"])!="els-local-oneclick-v1"||!RecoveryEqual(j["token"],identity["token"])||!RecoveryEqual(j["created"],identity["created"])||Convert.ToString(j["journal"])!=path)throw new IOException("Raw recovery journal identity differs");
            if(!NextAccessoryCohort.SourceReady||Convert.ToString(j["nine_source_binding_sha256"])!=NextAccessoryCohort.SourceSetHash||Convert.ToString(j["target"])!=commit||!String.Equals(Path.GetFullPath(Convert.ToString(j["repository"])),Path.GetFullPath(repository),StringComparison.OrdinalIgnoreCase))throw new IOException("Raw recovery source differs");
            var source=SourceUpdate.CaptureLocalCohort(repository);if(!NextAccessoryCohort.IsSource(source)||source.Commit!=commit)throw new IOException("Raw recovery Git cohort differs");
            var current=RecoveryDoc(Path.Combine(root,"releases","local","current.json"));object candidate,guarded;
            if(!RecoveryEqual(current,j["parent"])&&!(j.TryGetValue("candidate",out candidate)&&RecoveryEqual(current,candidate))&&!(j.TryGetValue("nine_guarded_candidate",out guarded)&&RecoveryEqual(current,guarded)))throw new IOException("Foreign raw current blocks recovery");
            var parent=(Dictionary<string,object>)j["parent"];if(Convert.ToString(parent["channel"])!="local")throw new IOException("Wrong raw parent channel");
            string retained=RecoveryUnder(root,Convert.ToString(parent["path"]));
            if(!retained.StartsWith(Path.Combine(root,"releases","local")+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)||RecoveryHash(RecoveryUnder(retained,"local-business-manifest.json"))!=Convert.ToString(parent["manifest_sha256"]))throw new IOException("Retained raw parent differs");
            var bundle=RecoveryDoc(RecoveryUnder(retained,"client-bundle-manifest.json"));var names=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach(Dictionary<string,object> row in (System.Collections.IEnumerable)bundle["files"]) {
                string name=Convert.ToString(row["path"]);if(!names.Add(name)||(name.StartsWith("state/",StringComparison.OrdinalIgnoreCase)&&name!="state/friends-client.example.json"))throw new IOException("Unexpected raw parent member");
                string file=RecoveryUnder(retained,name);if(new FileInfo(file).Length!=Convert.ToInt64(row["size"])||RecoveryHash(file)!=Convert.ToString(row["sha256"]))throw new IOException("Retained raw parent member changed");
            }
            if(!names.Contains("python/python.exe")||!names.Contains("els_server/application.py"))throw new IOException("Missing retained raw interpreter");
            SourceUpdate.RequireLocalSnapshot(source);return retained;
        }

        static string RawRecoveryRoot(string workspace,string repository,string commit) {
            string root=Path.GetFullPath(workspace),ownerRoot=Path.Combine(root,"analysis","coordination-20261015");
            Dictionary<string,object> identity=null;
            foreach(string name in new[]{"active-publication.lock","publication-record.lock"}) {
                string file=Path.Combine(ownerRoot,name);if(!File.Exists(file))continue;
                var item=RecoveryDoc(file);if(identity!=null&&!RecoveryEqual(identity,item))throw new IOException("Raw recovery locks disagree");identity=item;
            }
            if(identity==null)return null;
            if(Convert.ToString(identity["schema"])!="els-local-oneclick-v1"||Convert.ToString(identity["operation"])!="local-oneclick-updater")throw new IOException("Foreign raw recovery owner");
            string path=Convert.ToString(identity["journal"]),journal=Path.GetFullPath(path);
            if(!Path.IsPathRooted(path)||!String.Equals(path,journal,StringComparison.OrdinalIgnoreCase)||Path.GetFileName(journal)!="journal.json"||!journal.StartsWith(Path.Combine(root,"state","local-updater")+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Invalid raw recovery journal location");
            var j=RecoveryDoc(journal);
            if(Convert.ToInt32(j["nine_recovery_schema"])!=1||Convert.ToString(j["schema"])!="els-local-oneclick-v1"||!RecoveryEqual(j["token"],identity["token"])||!RecoveryEqual(j["created"],identity["created"])||Convert.ToString(j["journal"])!=path)throw new IOException("Raw recovery journal identity differs");
            if(!NextOwnedStonesCohort.SourceReady||Convert.ToString(j["nine_source_binding_sha256"])!=NextOwnedStonesCohort.SourceSetHash||Convert.ToString(j["target"])!=commit||!String.Equals(Path.GetFullPath(Convert.ToString(j["repository"])),Path.GetFullPath(repository),StringComparison.OrdinalIgnoreCase))throw new IOException("Raw recovery source differs");
            var source=SourceUpdate.CaptureLocalCohort(repository);if(!NextOwnedStonesCohort.IsSource(source)||source.Commit!=commit)throw new IOException("Raw recovery Git cohort differs");
            var current=RecoveryDoc(Path.Combine(root,"releases","local","current.json"));object candidate,guarded;
            if(!RecoveryEqual(current,j["parent"])&&!(j.TryGetValue("candidate",out candidate)&&RecoveryEqual(current,candidate))&&!(j.TryGetValue("nine_guarded_candidate",out guarded)&&RecoveryEqual(current,guarded)))throw new IOException("Foreign raw current blocks recovery");
            var parent=(Dictionary<string,object>)j["parent"];if(Convert.ToString(parent["channel"])!="local")throw new IOException("Wrong raw parent channel");
            string retained=RecoveryUnder(root,Convert.ToString(parent["path"]));
            if(!retained.StartsWith(Path.Combine(root,"releases","local")+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)||RecoveryHash(RecoveryUnder(retained,"local-business-manifest.json"))!=Convert.ToString(parent["manifest_sha256"]))throw new IOException("Retained raw parent differs");
            var bundle=RecoveryDoc(RecoveryUnder(retained,"client-bundle-manifest.json"));var names=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach(Dictionary<string,object> row in (System.Collections.IEnumerable)bundle["files"]) {
                string name=Convert.ToString(row["path"]);if(!names.Add(name)||(name.StartsWith("state/",StringComparison.OrdinalIgnoreCase)&&name!="state/friends-client.example.json"))throw new IOException("Unexpected raw parent member");
                string file=RecoveryUnder(retained,name);if(new FileInfo(file).Length!=Convert.ToInt64(row["size"])||RecoveryHash(file)!=Convert.ToString(row["sha256"]))throw new IOException("Retained raw parent member changed");
            }
            if(!names.Contains("python/python.exe")||!names.Contains("els_server/application.py"))throw new IOException("Missing retained raw interpreter");
            SourceUpdate.RequireLocalSnapshot(source);return retained;
        }

        public static object Run(string workspace,string repository,string commit,string client,Action<int,string> progress) {
            string prior=LaunchMode.LocalRoot,root;bool accessory=SourceUpdate.CaptureLocalCohort(repository).Accessory;
            try{root=accessory?AccessoryRawRecoveryRoot(workspace,repository,commit):RawRecoveryRoot(workspace,repository,commit);if(root==null){LaunchMode.LocalRoot=workspace;root=LaunchMode.ResolveLocal();}}finally{LaunchMode.LocalRoot=prior;}
            if(String.IsNullOrEmpty(accessory?NextAccessoryCohort.RawUpdaterHash:NextOwnedStonesCohort.RawUpdaterHash))throw new IOException("Owned stones raw updater bindings pending");
            string text=ComponentRuntime.VerifiedLocalResource(accessory?NextAccessoryCohort.RawUpdaterResource:NextOwnedStonesCohort.RawUpdaterResource,accessory?NextAccessoryCohort.RawUpdaterHash:NextOwnedStonesCohort.RawUpdaterHash);
            string digest;using(var bytes=new MemoryStream(Encoding.UTF8.GetBytes(text)))digest=Program.Hash(bytes);
            string folder=Path.Combine(Program.DataRoot,"local-updater"),script=Path.Combine(folder,"installer-"+digest+".py");
            if(!File.Exists(script)||File.ReadAllText(script,Encoding.UTF8)!=text)Program.PrivateWrite(script,text);
            string nonce=Guid.NewGuid().ToString("N"),request=Path.Combine(folder,"request-"+nonce+".json"),result=Path.Combine(folder,"result-"+nonce+".json"),log=Path.Combine(folder,"install-"+nonce+".log");
            Program.PrivateWrite(request,Program.Json.Serialize(new {workspace=workspace,repository=repository,commit=commit,client=client}));
            var info=new ProcessStartInfo(Path.Combine(root,"python","python.exe"),"-B -X utf8 "+Program.Quote(script)+" --request "+Program.Quote(request)+" --result "+Program.Quote(result)) {
                WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8
            };
            info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"]="1";
            using(var writer=new StreamWriter(log,false,Encoding.UTF8))using(var process=new Process {StartInfo=info}) {
                DataReceivedEventHandler receive=delegate(object sender,DataReceivedEventArgs e){
                    if(e.Data==null)return;lock(writer){writer.WriteLine(e.Data);writer.Flush();}
                    const string marker="ELS_UPDATE_PROGRESS:";
                    if(e.Data.StartsWith(marker,StringComparison.Ordinal))try{
                        var update=new System.Web.Script.Serialization.JavaScriptSerializer().Deserialize<Dictionary<string,object>>(e.Data.Substring(marker.Length));
                        progress(Convert.ToInt32(update["percent"]),Convert.ToString(update["message"]));
                    }catch{}
                };
                process.OutputDataReceived+=receive;process.ErrorDataReceived+=receive;
                process.Start();process.BeginOutputReadLine();process.BeginErrorReadLine();process.WaitForExit();
                if(!File.Exists(result))throw new IOException("自动更新中断。再次点击将核收恢复记录；账号和存档不会用旧备份覆盖。");
                var final=Program.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(result,Encoding.UTF8));
                if(process.ExitCode!=0||!Program.Ok(final))throw new IOException(final.ContainsKey("error")?Convert.ToString(final["error"]):"安装未完成，原运行版已保留。");
                return final;
            }
        }
    }
}
