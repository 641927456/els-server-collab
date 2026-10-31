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
        internal const string STRUCTUREManagedRelease="local-git-first-run-server-structure-20261029-v1",STRUCTUREBootstrapHash="394aa36f311dc6f8682111ab438f103760b067f2164894359ce16fe0d7ae573e";
        internal const string RepairManagedRelease="local-git-first-run-shared-repair-20261030-v1",RepairBootstrapHash="133cd860c9a76f03bfbc3f8519cb332ea0411f8eb578d6fb4b5275e15596d26c",RepairBootstrapResource="ElsFriends.RepairLocalBootstrap";
        static string SelectedText(Dictionary<string,object> doc,string key) {
            object value;if(!doc.TryGetValue(key,out value)||!(value is string))throw new IOException("Missing managed LOCAL identity: "+key);return (string)value;
        }
        static void RequireManagedDirection(string workspace,LocalCohortSnapshot source) {
            SourceUpdate.RequireKnownCohort(source);
            string path=Path.Combine(workspace,"releases","local","current.json");if(!File.Exists(path))return;
            if(new FileInfo(path).Length>1024*1024)throw new IOException("Oversized existing LOCAL pointer");
            var pointer=Program.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));
            string release=SelectedText(pointer,"release"),rid=SelectedText(pointer,"source_release"),formal=SelectedText(pointer,"source_formal_manifest_sha256");
            if(GroupWearRuntimeCohort.RequireCurrentDirection(pointer,source))return;
            if(QuestRuntimeCohort.RequireCurrentDirection(pointer,source))return;
            if(MapTriggerRuntimeCohort.RequireCurrentDirection(pointer,source))return;
            if(LoginRuntimeCohort.RequireCurrentDirection(pointer,source))return;
            if(WorldRuntimeCohort.RequireCurrentDirection(pointer,source))return;
            if(WearRuntimeCohort.RequireCurrentDirection(pointer,source))return;
            if(NextAccessoryCohort.RequireCurrentDirection(pointer,source))return;
            if(source.Accessory&&NextOwnedStonesCohort.SourceReady&&release==NextOwnedStonesCohort.ManagedRelease&&rid==NextOwnedStonesCohort.Release&&formal==NextOwnedStonesCohort.FormalHash)return;
            if(source.Accessory&&NextCacheCohort.SourceReady&&release==NextCacheCohort.ManagedRelease&&rid==NextCacheCohort.Release&&formal==NextCacheCohort.FormalHash)return;
            if(NextOwnedStonesCohort.RequireCurrentDirection(pointer,source))return;
            if(source.OwnedStones&&NextCacheCohort.SourceReady&&release==NextCacheCohort.ManagedRelease&&rid==NextCacheCohort.Release&&formal==NextCacheCohort.FormalHash)return;
            if(NextCacheCohort.RequireCurrentDirection(pointer,source))return;
            bool old=release==LegacyManagedRelease&&rid==SourceUpdate.LegacyRelease&&formal==SourceUpdate.LegacyFormal;
            bool current=release==IdentityManagedRelease&&rid==SourceUpdate.IdentityRelease&&formal==SourceUpdate.IdentityFormal;
            bool structure=release==STRUCTUREManagedRelease&&rid==SourceUpdate.STRUCTURERelease&&formal==SourceUpdate.STRUCTUREFormal;
            bool repair=SourceUpdate.RepairBindingsReady&&release==RepairManagedRelease&&rid==SourceUpdate.RepairRelease&&formal==SourceUpdate.RepairFormal;
            bool guarded=source.Repair&&SourceUpdate.RepairBindingsReady&&rid==SourceUpdate.RepairRelease&&formal==SourceUpdate.RepairFormal&&System.Text.RegularExpressions.Regex.IsMatch(release??"","^"+System.Text.RegularExpressions.Regex.Escape(RepairManagedRelease)+"-guarded-[a-f0-9]{12}$")&&SelectedText(pointer,"recovery_of")==RepairManagedRelease;
            if(guarded) { foreach(string key in new[]{"recovery_only","compatible_read_only","complete_C3_reader_and_data","all_three_guards"}) { object value;if(!pointer.TryGetValue(key,out value)||!(value is bool)||(bool)value!=true)throw new IOException("Invalid Repair recovery-only pointer"); } return; }
            if((!old&&!current&&!structure&&!repair)||(source.Legacy&&!old)||(!source.Legacy&&!source.Structural&&!source.Repair&&!source.Cache41400&&!source.OwnedStones&&!source.Accessory&&(structure||repair))||(source.Structural&&repair))throw new IOException("Existing managed LOCAL source cannot be downgraded or replaced by an unknown cohort");
        }
        static void RequireSelectedMetadata(string runtime,RuntimeDefinition definition,LocalCohortSnapshot source) {
            string path=Path.Combine(runtime,"local-bootstrap-source.json");if(!File.Exists(path)||new FileInfo(path).Length>4*1024*1024)throw new IOException("Missing or oversized signed LOCAL source metadata");
            byte[] raw=File.ReadAllBytes(path);string hash;using(var data=new MemoryStream(raw))hash=Program.Hash(data);
            if(!definition.Files.Exists(f=>f.Path=="local-bootstrap-source.json"&&f.Hash==hash&&f.Size==raw.Length))throw new IOException("LOCAL metadata is outside the selected signed definition");
            var metadata=new System.Web.Script.Serialization.JavaScriptSerializer {MaxJsonLength=4*1024*1024}.Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(raw));
            object count;if(SelectedText(metadata,"source_release")!=source.SourceRelease||SelectedText(metadata,"source_formal_manifest_sha256")!=source.FormalHash||SelectedText(metadata,"profile")!=source.Profile||SelectedText(metadata,"source_files_sha256")!=source.SourceRowsHash||!metadata.TryGetValue("source_file_count",out count)||!(count is int)||(int)count!=(source.Accessory?NextAccessoryCohort.SourceCount:source.OwnedStones?NextOwnedStonesCohort.SourceCount:source.Cache41400?NextCacheCohort.SourceCount:source.Repair?SourceUpdate.RepairSourceCount.Value:source.Structural?1332:1325)||SelectedText(metadata,"release")!=(source.Accessory?GroupWearRuntimeCohort.ManagedRelease:source.OwnedStones?NextOwnedStonesCohort.ManagedRelease:source.Cache41400?NextCacheCohort.ManagedRelease:source.Repair?RepairManagedRelease:source.Structural?STRUCTUREManagedRelease:source.Legacy?LegacyManagedRelease:IdentityManagedRelease))throw new IOException("Signed LOCAL metadata differs from the pinned Git cohort");
        }
        public static string Run(string repository,Action<int,string> progress) {
            repository=SourceUpdate.Validate(repository);
            var selection=SourceUpdate.CaptureLocalCohort(repository);
            string commit=selection.Commit,workspace=Workspace(repository);RequireManagedDirection(workspace,selection);
            var definition=ComponentRuntime.SelectLocalDefinition(selection);
            // Existing pointers are resolved by the normal mode path. Never overwrite one here.
            progress(5,"正在准备已签名的本地运行环境…");
            string runtime=ComponentRuntime.EnsureSelectedLocal(definition,selection,message=>progress(10,message));
            SourceUpdate.RequireLocalSnapshot(selection);RequireManagedDirection(workspace,selection);RequireSelectedMetadata(runtime,definition,selection);
            string folder=Path.Combine(LaunchMode.SharedDataRoot,"local-bootstrap",Guid.NewGuid().ToString("N"));Directory.CreateDirectory(folder);
            string script=Path.Combine(folder,"local_bootstrap.py"),manifest=Path.Combine(folder,"verified-runtime-files.json"),result=Path.Combine(folder,"result.json"),log=Path.Combine(folder,"bootstrap.log");
            string text=ComponentRuntime.VerifiedLocalResource(selection.Accessory?GroupWearRuntimeCohort.BootstrapResource:selection.OwnedStones?NextOwnedStonesCohort.BootstrapResource:selection.Cache41400?NextCacheCohort.BootstrapResource:selection.Repair?RepairBootstrapResource:selection.Structural?"ElsFriends.STRUCTURELocalBootstrap":selection.Legacy?"ElsFriends.LegacyLocalBootstrap":"ElsFriends.LocalBootstrap",selection.Accessory?GroupWearRuntimeCohort.BootstrapHash:selection.OwnedStones?NextOwnedStonesCohort.BootstrapHash:selection.Cache41400?NextCacheCohort.BootstrapHash:selection.Repair?RepairBootstrapHash:selection.Structural?STRUCTUREBootstrapHash:selection.Legacy?LegacyBootstrapHash:IdentityBootstrapHash);
            if(!selection.Legacy)Program.PrivateWrite(Path.Combine(folder,"local_updater.py"),ComponentRuntime.VerifiedLocalResource("ElsFriends.LocalUpdater",ManagedUpdaterHash));
            if(selection.Accessory){Program.PrivateWrite(Path.Combine(folder,"accessory-predecessor-a.txt"),ComponentRuntime.VerifiedLocalResource("ElsFriends.AccessoryPredecessorA","1bb578d4f823db385caa49f7657feb9893c12153ec5dc557eba1ecc8c2f9fa62"));Program.PrivateWrite(Path.Combine(folder,"accessory-predecessor-b.txt"),ComponentRuntime.VerifiedLocalResource("ElsFriends.AccessoryPredecessorB","a178e771ba22bac3a2757cae88e65a8f580f9955f5f3d2ea76161a11260ec679"));}
            if(selection.Accessory)Program.PrivateWrite(Path.Combine(folder,"wear-predecessor.txt"),ComponentRuntime.VerifiedLocalResource("ElsFriends.WearPredecessor","68b74b889731569534bf952510dd61402669aa605bc878e9fa4e2aa80184fe7c"));
            if(selection.Accessory)Program.PrivateWrite(Path.Combine(folder,"world-predecessor.txt"),ComponentRuntime.VerifiedLocalResource("ElsFriends.WorldPredecessor","fac2c5f0afdf3cee8593a03af0ce919a754bbef27d0d3b2807720d785faad4fd"));
            if(selection.Accessory)Program.PrivateWrite(Path.Combine(folder,"login-predecessor.txt"),ComponentRuntime.VerifiedLocalResource("ElsFriends.LoginPredecessor","354920a6e9bd854d654ba93bb1ff61032bc828979ef0f256b6c5e510dd5c8e20"));
            if(selection.Accessory)Program.PrivateWrite(Path.Combine(folder,"map-trigger-predecessor.txt"),ComponentRuntime.VerifiedLocalResource("ElsFriends.MapTriggerPredecessor","02d6907bc4e461dbcf3653901fc5dc1585b496af0cbcdff66d75b5b7bef186e6"));
            if(selection.Accessory)Program.PrivateWrite(Path.Combine(folder,"quest-predecessor.txt"),ComponentRuntime.VerifiedLocalResource("ElsFriends.QuestPredecessor","5cc5bc4d8d855fc1460209504614080490cc5134cdc72fd979e83888a3cfeee5"));
            if(selection.Accessory)Program.PrivateWrite(Path.Combine(folder,"group-wear-predecessor.txt"),ComponentRuntime.VerifiedLocalResource("ElsFriends.GroupWearPredecessor","8057f9ff10baf637c3ca4ad1f63afbd8a7a0a52119d4e89bccbc53b5009e9eff"));
            Program.PrivateWrite(script,text);Program.PrivateWrite(manifest,ComponentRuntime.SelectedLocalFileManifest(runtime,definition,selection));
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
