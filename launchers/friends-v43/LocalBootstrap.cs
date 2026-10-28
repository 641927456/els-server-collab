using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;

namespace ElsFriends {
    static class LocalBootstrap {
        public const string PayloadHash = "c2479938972ae6f9c6f3747d2348f28473dbaa2635ee93e16c1b9239e309f86e";
        public static bool Installed(string root) {return !String.IsNullOrWhiteSpace(root)&&File.Exists(Path.Combine(root,"releases","local","current.json"));}
        public static string Workspace(string repository) {return Path.Combine(repository,".runtime-cache","unified-local");}
        public static bool IsManagedWorkspace(string workspace) {
            if(String.IsNullOrWhiteSpace(workspace))return false;
            var directory=new DirectoryInfo(Path.GetFullPath(workspace));
            if(directory.Name.Equals("unified-local",StringComparison.OrdinalIgnoreCase)&&directory.Parent!=null&&directory.Parent.Name.Equals(".runtime-cache",StringComparison.OrdinalIgnoreCase))return true;
            if(!Installed(workspace))return false;
            var pointer=Program.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(workspace,"releases","local","current.json"),Encoding.UTF8));
            object value;return pointer.TryGetValue("first_initialization",out value)&&Object.Equals(value,true);
        }
        public static void RequireRepository(string workspace,string repository) {
            if(IsManagedWorkspace(workspace)&&!String.Equals(Path.GetFullPath(workspace),Path.GetFullPath(Workspace(repository)),StringComparison.OrdinalIgnoreCase))throw new IOException("此本地安装属于另一个 Git 仓库，请选择最初初始化时使用的仓库目录。");
        }
        public static string FindRepository(string source) {
            var candidates=new List<string>();
            if(!String.IsNullOrEmpty(LaunchMode.LocalSource))candidates.Add(LaunchMode.LocalSource);
            if(!String.IsNullOrEmpty(source))candidates.Add(source);
            candidates.Add(Environment.CurrentDirectory);
            for(var dir=new DirectoryInfo(AppDomain.CurrentDomain.BaseDirectory);dir!=null;dir=dir.Parent)candidates.Add(dir.FullName);
            foreach(string candidate in candidates)try {return SourceUpdate.Validate(candidate);}catch{}
            return null;
        }
        internal const string LegacyBootstrapHash="5a79b3d100b449a5f3eb6fb2cf0fff386e44ddf4fe5a1aceac3e66b6aaeac905";
        internal const string IdentityBootstrapHash="24f1bde4e963528db97a8dbbd477d9ff7ae3c063a924f8b2fe820621523a7fe0";
        internal const string LegacyManagedRelease="local-git-first-run-20261029-v1",IdentityManagedRelease="local-git-first-run-identity-20261029-v1";
        internal const string ManagedUpdaterHash="c976b8c28c85d54b128ac0943e1abf20969859c5139b7e3b5ece98bead049fc2";
        static string SelectedText(Dictionary<string,object> doc,string key) {
            object value;if(!doc.TryGetValue(key,out value)||!(value is string))throw new IOException("Missing managed LOCAL identity: "+key);return (string)value;
        }
        static void RequireManagedDirection(string workspace,LocalCohortSnapshot source) {
            string path=Path.Combine(workspace,"releases","local","current.json");if(!File.Exists(path))return;
            if(new FileInfo(path).Length>1024*1024)throw new IOException("Oversized existing LOCAL pointer");
            var pointer=Program.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));
            string release=SelectedText(pointer,"release"),rid=SelectedText(pointer,"source_release"),formal=SelectedText(pointer,"source_formal_manifest_sha256");
            bool old=release==LegacyManagedRelease&&rid==SourceUpdate.LegacyRelease&&formal==SourceUpdate.LegacyFormal;
            bool current=release==IdentityManagedRelease&&rid==SourceUpdate.IdentityRelease&&formal==SourceUpdate.IdentityFormal;
            if((!old&&!current)||(source.Legacy&&!old))throw new IOException("Existing managed LOCAL source cannot be downgraded or replaced by an unknown cohort");
        }
        static void RequireSelectedMetadata(string runtime,RuntimeDefinition definition,LocalCohortSnapshot source) {
            string path=Path.Combine(runtime,"local-bootstrap-source.json");if(!File.Exists(path)||new FileInfo(path).Length>4*1024*1024)throw new IOException("Missing or oversized signed LOCAL source metadata");
            byte[] raw=File.ReadAllBytes(path);string hash;using(var data=new MemoryStream(raw))hash=Program.Hash(data);
            if(!definition.Files.Exists(f=>f.Path=="local-bootstrap-source.json"&&f.Hash==hash&&f.Size==raw.Length))throw new IOException("LOCAL metadata is outside the selected signed definition");
            var metadata=new System.Web.Script.Serialization.JavaScriptSerializer {MaxJsonLength=4*1024*1024}.Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(raw));
            object count;if(SelectedText(metadata,"source_release")!=source.SourceRelease||SelectedText(metadata,"source_formal_manifest_sha256")!=source.FormalHash||SelectedText(metadata,"profile")!=source.Profile||SelectedText(metadata,"source_files_sha256")!=source.SourceRowsHash||!metadata.TryGetValue("source_file_count",out count)||!(count is int)||(int)count!=1325||SelectedText(metadata,"release")!=(source.Legacy?LegacyManagedRelease:IdentityManagedRelease))throw new IOException("Signed LOCAL metadata differs from the pinned Git cohort");
        }
        public static string Run(string repository,Action<int,string> progress) {
            repository=SourceUpdate.Validate(repository);
            var selection=SourceUpdate.CaptureLocalCohort(repository);
            string commit=selection.Commit,workspace=Workspace(repository);RequireManagedDirection(workspace,selection);
            var definition=ComponentRuntime.SelectLocalDefinition(selection.Legacy);
            // Existing pointers are resolved by the normal mode path. Never overwrite one here.
            progress(5,"正在准备已签名的本地运行环境…");
            string runtime=ComponentRuntime.EnsureSelectedLocal(definition,selection.Legacy,message=>progress(10,message));
            SourceUpdate.RequireLocalSnapshot(selection);RequireManagedDirection(workspace,selection);RequireSelectedMetadata(runtime,definition,selection);
            string folder=Path.Combine(LaunchMode.SharedDataRoot,"local-bootstrap",Guid.NewGuid().ToString("N"));Directory.CreateDirectory(folder);
            string script=Path.Combine(folder,"local_bootstrap.py"),manifest=Path.Combine(folder,"verified-runtime-files.json"),result=Path.Combine(folder,"result.json"),log=Path.Combine(folder,"bootstrap.log");
            string text=ComponentRuntime.VerifiedLocalResource(selection.Legacy?"ElsFriends.LegacyLocalBootstrap":"ElsFriends.LocalBootstrap",selection.Legacy?LegacyBootstrapHash:IdentityBootstrapHash);
            if(!selection.Legacy)Program.PrivateWrite(Path.Combine(folder,"local_updater.py"),ComponentRuntime.VerifiedLocalResource("ElsFriends.LocalUpdater",ManagedUpdaterHash));
            Program.PrivateWrite(script,text);Program.PrivateWrite(manifest,ComponentRuntime.SelectedLocalFileManifest(runtime,definition,selection.Legacy));
            string arguments="-B -X utf8 "+Program.Quote(script)+" --runtime "+Program.Quote(runtime)+" --workspace "+Program.Quote(workspace)+" --repository "+Program.Quote(repository)+" --commit "+Program.Quote(commit)+" --runtime-manifest "+Program.Quote(manifest)+" --result "+Program.Quote(result);
            var info=new ProcessStartInfo(Path.Combine(runtime,"python","python.exe"),arguments) {WorkingDirectory=runtime,UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden,RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8};
            info.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"]="1";
            using(var writer=new StreamWriter(log,false,Encoding.UTF8))using(var process=new Process {StartInfo=info}) {
                DataReceivedEventHandler receive=delegate(object sender,DataReceivedEventArgs e) {
                    if(e.Data==null)return;lock(writer){writer.WriteLine(e.Data);writer.Flush();}
                    const string marker="ELS_BOOTSTRAP_PROGRESS:";
                    if(e.Data.StartsWith(marker,StringComparison.Ordinal))try {var item=Program.Json.Deserialize<Dictionary<string,object>>(e.Data.Substring(marker.Length));progress(Convert.ToInt32(item["percent"]),Convert.ToString(item["message"]));}catch{}
                };
                process.OutputDataReceived+=receive;process.ErrorDataReceived+=receive;
                SourceUpdate.RequireLocalSnapshot(selection);RequireManagedDirection(workspace,selection);process.Start();process.BeginOutputReadLine();process.BeginErrorReadLine();process.WaitForExit();
                if(!File.Exists(result))throw new IOException("本地初始化中断，原有存档保持。请重试；诊断："+log);
                var final=new System.Web.Script.Serialization.JavaScriptSerializer {MaxJsonLength=4*1024*1024}.Deserialize<Dictionary<string,object>>(File.ReadAllText(result,Encoding.UTF8));
                if(process.ExitCode!=0||!Program.Ok(final))throw new IOException(final.ContainsKey("error")?Convert.ToString(final["error"]):"本地初始化未完成，请查看诊断后重试。");
                if(!String.Equals(Path.GetFullPath(Convert.ToString(final["workspace"])),Path.GetFullPath(workspace),StringComparison.OrdinalIgnoreCase)||!Installed(workspace))throw new IOException("本地安装目录核验失败。");
                SourceUpdate.RequireLocalSnapshot(selection);
                string old=LaunchMode.LocalRoot;try{LaunchMode.LocalRoot=workspace;LaunchMode.ResolveLocal();}finally{LaunchMode.LocalRoot=old;}
                progress(100,"本地版本已准备完成，请选择客户端并开始游戏。");return workspace;
            }
        }
    }
}
