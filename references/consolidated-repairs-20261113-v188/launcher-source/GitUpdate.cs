using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace ElsFriends {
    // One clean Git snapshot selects exactly one signed LOCAL source cohort.
    sealed class LocalCohortSnapshot {
        public readonly string Repository,Commit,Profile,ProfileHash,SourceRelease,FormalHash,SourceRowsHash;
        public readonly bool Legacy;
        internal bool Structural {get{return Profile==SourceUpdate.STRUCTUREProfile;}}
        internal bool Repair {get{return SourceUpdate.IsRepair(this);}}
        internal bool Cache41400 {get{return NextCacheCohort.IsSource(this);}}
        internal bool Accessory {get{return NextAccessoryCohort.IsSource(this);}}
        internal bool OwnedStones {get{return NextOwnedStonesCohort.IsSource(this);}}
        internal LocalCohortSnapshot(string repository,string commit,bool legacy,string profile,string profileHash,string sourceRelease,string formalHash,string sourceRowsHash) {
            Repository=repository;Commit=commit;Legacy=legacy;Profile=profile;ProfileHash=profileHash;SourceRelease=sourceRelease;FormalHash=formalHash;SourceRowsHash=sourceRowsHash;
        }
    }
    // Pull a source checkout only. Promoted runtimes and saves are never copied.
    static class SourceUpdate {
        static readonly string NoHooks=Path.Combine(Path.GetTempPath(),"els-no-git-hooks-"+Guid.NewGuid().ToString("N"));
        // All source operations, including Pull before LOCAL selection, use the same cwd-owned Git context.
        static void CleanGitEnvironment(ProcessStartInfo info) {
            foreach(string key in info.EnvironmentVariables.Keys.Cast<string>().Where(k=>k.StartsWith("GIT_",StringComparison.OrdinalIgnoreCase)).ToArray())info.EnvironmentVariables.Remove(key);
            info.EnvironmentVariables["GIT_TERMINAL_PROMPT"]="0";info.EnvironmentVariables["GCM_INTERACTIVE"]="never";
        }
        static string Git(string root, params string[] args) {
            var info=new ProcessStartInfo("git", "-c core.hooksPath="+Program.Quote(NoHooks)+" -c core.fsmonitor=false "+String.Join(" ",args.Select(Program.Quote))) {
                WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,
                RedirectStandardOutput=true,RedirectStandardError=true,
                StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8
            };
            CleanGitEnvironment(info); // Shared source commands: root, HEAD, status and Pull.
            using(var process=Process.Start(info)) {
                var output=process.StandardOutput.ReadToEndAsync();var error=process.StandardError.ReadToEndAsync();
                if(!process.WaitForExit(120000)){process.Kill();process.WaitForExit();throw new IOException("Git 操作超时，请检查网络后重试。");}
                Task.WaitAll(output,error);
                if(process.ExitCode!=0)throw new IOException("Git 操作未完成。请检查仓库权限、网络和分支状态；未执行强制覆盖。");
                return output.Result.Trim();
            }
        }
        internal const string LegacyProfile="channels/native-force-guild-flow-accepted-20261029-v1.json",IdentityProfile="channels/native-unit-account-identity-accepted-20261029-v1.json";
        internal const string LegacyProfileHash="77fb1412039711eaba1160f03f96cdd61bfb3fdde54df3c08491281f0ac448b9",IdentityProfileHash="27c1895d03893cb5ffb79b4a7a84ebcedd501f25efb981fe2a0b5b3a16cbffe8";
        internal const string LegacyRelease="local-native-shop-flow-20261029-v1",IdentityRelease="local-native-unit-account-identity-20261029-v1";
        internal const string LegacyFormal="d621337b400fc4dfe3a61bd32be2180bd98c55e4c8ab2beba3eae2e3e2b91b11",IdentityFormal="7c72970e3e5781c43a32d3f748d32c14fcedfe0b4f3f3fd660086a2cfcbf9f5e";
        internal const string LegacyRows="7900ad4eef4985b6b953b00e880f8b303224e0bb97debd59e178057301de3cdb",IdentityRows="b36e18da6a4a3729d8a3b8dd20f4a486906cbd88e62158c2a97d893b2cbe49b8";

        internal const string STRUCTUREProfile="channels/server-structure-accepted-20261029-v1.json",STRUCTUREProfileHash="05e234b9d1b055c1f991bea500d9d0f8ec15203a44cad33ccd6627de2f6b6a42",STRUCTURERelease="local-native-server-structure-20261029-v1",STRUCTUREFormal="b014a2cfaab3968fb16055f85cbe35803b5cb5d1369382ee7ba5b6193dda43f2",STRUCTURERows="6dc7ebde683c9ebea3d0327be7c7e46c3a1fd3843783869d05ddec4dc295f461";
        // Pending fourth source descriptor: no current C2 hash is a final C3 binding.
        internal const string RepairProfile="channels/native-shared-repair-accepted-20261030-v1.json",RepairProfileHash="c63fbed4110c2b6a3f597d305c12971690fe78a6d00c4d2ecc285e039fe001ac",RepairRelease="local-native-shared-repair-20261030-v1",RepairFormal="2291d8c2e24f72209e802de082fda701f623fc87609e201206136f5862ff9fd5",RepairRows="3e8430e117e2cc370801c06a7d62f54c10ee3fa4d4357ebccfc4f40231701947",RepairSourceSet="8ed8f297ea7f7bbaccb750985bf27302e38ca9ec00afa9f874c03f3cbff38adc";
        internal static readonly int? RepairSourceCount=1340;
        static bool BoundRepairHash(string value) {return System.Text.RegularExpressions.Regex.IsMatch(value??"","^[a-f0-9]{64}$");}
        internal static bool RepairBindingsReady {get{return !String.IsNullOrEmpty(RepairProfile)&&!String.IsNullOrEmpty(RepairRelease)&&BoundRepairHash(RepairProfileHash)&&BoundRepairHash(RepairFormal)&&BoundRepairHash(RepairRows)&&BoundRepairHash(RepairSourceSet)&&RepairSourceCount.HasValue;}}
        internal static bool IsRepair(LocalCohortSnapshot source) {return source!=null&&RepairBindingsReady&&!source.Legacy&&source.Profile==RepairProfile&&source.ProfileHash==RepairProfileHash&&source.SourceRelease==RepairRelease&&source.FormalHash==RepairFormal&&source.SourceRowsHash==RepairRows;}
        internal static void RequireKnownCohort(LocalCohortSnapshot source) {
            if(source==null)throw new IOException("Missing exact LOCAL source snapshot");
            bool legacy=source.Legacy&&source.Profile==LegacyProfile&&source.ProfileHash==LegacyProfileHash&&source.SourceRelease==LegacyRelease&&source.FormalHash==LegacyFormal&&source.SourceRowsHash==LegacyRows;
            bool identity=!source.Legacy&&source.Profile==IdentityProfile&&source.ProfileHash==IdentityProfileHash&&source.SourceRelease==IdentityRelease&&source.FormalHash==IdentityFormal&&source.SourceRowsHash==IdentityRows;
            bool structure=!source.Legacy&&source.Profile==STRUCTUREProfile&&source.ProfileHash==STRUCTUREProfileHash&&source.SourceRelease==STRUCTURERelease&&source.FormalHash==STRUCTUREFormal&&source.SourceRowsHash==STRUCTURERows;
            if(!legacy&&!identity&&!structure&&!IsRepair(source)&&!NextCacheCohort.IsSource(source)&&!NextOwnedStonesCohort.IsSource(source)&&!NextAccessoryCohort.IsSource(source))throw new IOException("Unknown or unbound exact LOCAL source descriptor");
        }
        static string CohortString(System.Collections.Generic.Dictionary<string,object> doc,string key) {
            object value;if(!doc.TryGetValue(key,out value)||!(value is string))throw new IOException("Missing LOCAL source identity: "+key);return (string)value;
        }
        static byte[] ReadPinnedLocalBlob(string root,string commit,string name) {
            if(!System.Text.RegularExpressions.Regex.IsMatch(commit??"","^[a-f0-9]{40}$")||(name!="channels/current-engine.json"&&name!=LegacyProfile&&name!=IdentityProfile&&name!=STRUCTUREProfile&&(!RepairBindingsReady||name!=RepairProfile)&&(!NextCacheCohort.SourceReady||name!=NextCacheCohort.Profile)&&(!NextOwnedStonesCohort.SourceReady||name!=NextOwnedStonesCohort.Profile)&&(!NextAccessoryCohort.SourceReady||name!=NextAccessoryCohort.Profile)))throw new IOException("Invalid pinned LOCAL Git object");
            var info=new ProcessStartInfo("git","-c core.hooksPath="+Program.Quote(NoHooks)+" -c core.fsmonitor=false cat-file blob "+Program.Quote(commit+":"+name)) {
                WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,StandardErrorEncoding=Encoding.UTF8
            };
            CleanGitEnvironment(info); // Pinned raw blob uses the identical sanitized context.
            using(var process=Process.Start(info)) {
                var output=Task.Factory.StartNew(delegate {using(var raw=new MemoryStream()){byte[] buffer=new byte[8192];int count;while((count=process.StandardOutput.BaseStream.Read(buffer,0,buffer.Length))>0){if(raw.Length+count>4*1024*1024)throw new IOException("LOCAL Git blob exceeds limit");raw.Write(buffer,0,count);}return raw.ToArray();}});
                var error=process.StandardError.ReadToEndAsync();
                if(!process.WaitForExit(120000)){process.Kill();process.WaitForExit();throw new IOException("LOCAL Git verification timed out");}
                Task.WaitAll(output,error);if(process.ExitCode!=0)throw new IOException("Pinned LOCAL Git object is unavailable");return output.Result;
            }
        }
        internal static void RequireLocalSnapshot(LocalCohortSnapshot source) {
            if(source==null||!String.Equals(Validate(source.Repository),source.Repository,StringComparison.OrdinalIgnoreCase)||CurrentCommit(source.Repository)!=source.Commit||Git(source.Repository,"status","--porcelain","--untracked-files=all","--ignore-submodules=all").Length!=0||CurrentCommit(source.Repository)!=source.Commit)throw new IOException("Git LOCAL source changed during preparation");
        }
        internal static LocalCohortSnapshot CaptureLocalCohort(string repository) {
            string root=Validate(repository),commit=CurrentCommit(root);
            var json=new System.Web.Script.Serialization.JavaScriptSerializer {MaxJsonLength=4*1024*1024,RecursionLimit=64};
            var initial=new LocalCohortSnapshot(root,commit,false,"","","","","");RequireLocalSnapshot(initial);
            var selected=json.Deserialize<System.Collections.Generic.Dictionary<string,object>>(Encoding.UTF8.GetString(ReadPinnedLocalBlob(root,commit,"channels/current-engine.json")));
            var accepted=(System.Collections.Generic.Dictionary<string,object>)selected["accepted"];
            var local=(System.Collections.Generic.Dictionary<string,object>)accepted["local"];
            string profile=CohortString(selected,"profile"),release=CohortString(local,"release"),formal=CohortString(local,"formal_manifest_sha256");
            bool legacy=profile==LegacyProfile&&release==LegacyRelease&&formal==LegacyFormal;
            bool identity=profile==IdentityProfile&&release==IdentityRelease&&formal==IdentityFormal;
            bool structure=profile==STRUCTUREProfile&&release==STRUCTURERelease&&formal==STRUCTUREFormal;
            bool repair=RepairBindingsReady&&profile==RepairProfile&&release==RepairRelease&&formal==RepairFormal;
            bool next=NextCacheCohort.SourceReady&&profile==NextCacheCohort.Profile&&release==NextCacheCohort.Release&&formal==NextCacheCohort.FormalHash;
            bool nine=NextOwnedStonesCohort.SourceReady&&profile==NextOwnedStonesCohort.Profile&&release==NextOwnedStonesCohort.Release&&formal==NextOwnedStonesCohort.FormalHash;
            bool accessory=NextAccessoryCohort.SourceReady&&profile==NextAccessoryCohort.Profile&&release==NextAccessoryCohort.Release&&formal==NextAccessoryCohort.FormalHash;
            if(!legacy&&!identity&&!structure&&!repair&&!next&&!nine&&!accessory)throw new IOException("This Git LOCAL source is not an exact accepted launcher cohort");
            string expected=accessory?NextAccessoryCohort.ProfileHash:nine?NextOwnedStonesCohort.ProfileHash:next?NextCacheCohort.ProfileHash:repair?RepairProfileHash:structure?STRUCTUREProfileHash:legacy?LegacyProfileHash:IdentityProfileHash;byte[] raw=ReadPinnedLocalBlob(root,commit,profile);
            using(var data=new MemoryStream(raw))if(Program.Hash(data)!=expected)throw new IOException("Git LOCAL profile raw bytes differ from the accepted cohort");
            var result=new LocalCohortSnapshot(root,commit,legacy,profile,expected,release,formal,accessory?NextAccessoryCohort.RowsHash:nine?NextOwnedStonesCohort.RowsHash:next?NextCacheCohort.RowsHash:repair?RepairRows:structure?STRUCTURERows:legacy?LegacyRows:IdentityRows);RequireKnownCohort(result);RequireLocalSnapshot(result);return result;
        }
        public static string Validate(string folder) {
            string root=Path.GetFullPath(folder).TrimEnd(Path.DirectorySeparatorChar);
            if(!Directory.Exists(root)||!File.Exists(Path.Combine(root,"els_server","application.py")))throw new IOException("请选择包含 els_server 的服务端 Git 仓库根目录。");
            if(!String.Equals(Path.GetFullPath(Git(root,"rev-parse","--show-toplevel")).TrimEnd(Path.DirectorySeparatorChar),root,StringComparison.OrdinalIgnoreCase))throw new IOException("请选择 Git 仓库根目录。");
            if(File.Exists(Path.Combine(root,"release-snapshot.json"))||Directory.Exists(Path.Combine(root,"releases","local")))throw new IOException("正式运行快照不能作为源码更新目录，请选择独立的 Git 工作目录。");
            return root;
        }
        public static string CurrentCommit(string root) {return Git(Validate(root),"rev-parse","HEAD^{commit}");}
        public static string Describe(string root) {return Git(Validate(root),"symbolic-ref","--quiet","--short","HEAD");}
        public static object Pull(string folder,Action<int,string> progress) {
            string root=Validate(folder);string gitdir=Git(root,"rev-parse","--absolute-git-dir");
            string lockPath=Path.Combine(gitdir,"els-launcher-update.lock");
            FileStream held;
            try{held=new FileStream(lockPath,FileMode.CreateNew,FileAccess.Write,FileShare.None);}catch(IOException){throw new IOException("这个仓库正在更新，请稍后重试。");}
            try {using(held) {
                progress(8,"正在检查本地改动…");
                foreach(string marker in new[]{"MERGE_HEAD","CHERRY_PICK_HEAD","REVERT_HEAD","rebase-merge","rebase-apply","index.lock"})
                    if(File.Exists(Path.Combine(gitdir,marker))||Directory.Exists(Path.Combine(gitdir,marker)))throw new IOException("仓库还有未完成的 Git 操作，请先处理。");
                if(Git(root,"status","--porcelain","--untracked-files=all").Length!=0)throw new IOException("本地有未提交的修改或新增文件，请先提交或自行保存后再更新。");
                string branch=Git(root,"symbolic-ref","--quiet","--short","HEAD");
                string remote=Git(root,"config","--get","branch."+branch+".remote");
                string merge=Git(root,"config","--get","branch."+branch+".merge");
                if(remote=="."||remote.StartsWith("-")||!merge.StartsWith("refs/heads/",StringComparison.Ordinal))throw new IOException("当前分支没有可拉取的远程上游。");
                string before=Git(root,"rev-parse","HEAD");
                progress(25,"正在拉取上游分支 "+branch+"…");
                // Fetch one configured branch, then pin FETCH_HEAD by full commit.
                Git(root,"fetch","--no-tags",remote,merge);
                string target=Git(root,"rev-parse","FETCH_HEAD^{commit}");
                progress(60,"正在核对更新范围…");
                if(Git(root,"status","--porcelain","--untracked-files=all").Length!=0||Git(root,"rev-parse","HEAD")!=before||Git(root,"symbolic-ref","--quiet","--short","HEAD")!=branch)throw new IOException("更新期间仓库发生变化，已停止安装。");
                if(before==target){progress(100,"当前分支已经是最新代码。");return new {ok=true,changed=false,branch=branch,before=before,after=before,source_only=true};}
                // merge-base exits nonzero for divergence; never merge or rebase it.
                Git(root,"merge-base","--is-ancestor",before,target);
                var paths=Git(root,"diff","--name-only",before,target).Split('\n');
                foreach(var item in paths) {
                    string path=item.Trim().Replace('\\','/').ToLowerInvariant();
                    if(path.StartsWith("state/")||path.StartsWith("releases/")||path.EndsWith(".sqlite3")||path.EndsWith(".sqlite")||path.EndsWith(".db")||path.EndsWith(".pem")||path.EndsWith(".key"))throw new IOException("上游涉及存档、发布目录或密钥，已停止自动更新，请交由维护者核收。");
                }
                progress(78,"正在保留更新前版本…");
                string backup="refs/launcher-backups/"+DateTime.UtcNow.ToString("yyyyMMdd-HHmmss")+"-"+Guid.NewGuid().ToString("N");
                Git(root,"update-ref",backup,before);
                progress(88,"正在以快进方式更新源码…");
                Git(root,"merge","--ff-only","--no-edit",target);
                string after=Git(root,"rev-parse","HEAD");if(after!=target)throw new IOException("代码版本核验未通过，请检查仓库。");
                progress(100,"源码拉取完成，继续自动检查和安装本地服务端…");
                return new {ok=true,changed=true,branch=branch,before=before,after=after,backup_ref=backup,source_only=true};
            }} finally {File.Delete(lockPath);}
        }
    }
}
