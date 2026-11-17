using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;

namespace ElsFriends {
    static class LaunchMode {
        public static bool Local;
        public static string LocalRoot;
        public static string LocalSource;
        public static readonly string SharedDataRoot=Program.DataRoot;
        public static string[] Parse(string[] args) {
            var rest=new List<string>();bool explicitMode=false;
            for(int i=0;i<args.Length;i++) {
                if(args[i]=="--local-source") {
                    if(++i>=args.Length||!Path.IsPathRooted(args[i]))throw new IOException("请选择服务端 Git 仓库根目录。");
                    LocalSource=Path.GetFullPath(args[i]);explicitMode=true;
                } else if(args[i]=="--local"){Local=true;explicitMode=true;}
                else if(args[i]=="--online"){Local=false;explicitMode=true;}
                else if(args[i]=="--local-root") {
                    if(++i>=args.Length||!Path.IsPathRooted(args[i]))throw new IOException("A local workspace is required");
                    LocalRoot=Path.GetFullPath(args[i]);
                } else rest.Add(args[i]);
            }
            if(!explicitMode&&(rest.Count==0||rest[0]=="--updated-parent"))RestorePreference();
            if(LocalSource!=null)Local=false; // First installation runs after the form is visible.
            if(Local) {
                if(LocalRoot==null)throw new IOException("A local workspace is required");
                ResolveLocal();
                Program.DataRoot=Path.Combine(LocalRoot,"state","unified-launcher");
            }
            return rest.ToArray();
        }
        public static string RestartArguments {get{if(LocalSource!=null)return " --local --local-source "+Program.Quote(LocalSource);return Local?" --local --local-root "+Program.Quote(LocalRoot):" --online"+(String.IsNullOrEmpty(LocalRoot)?"":" --local-root "+Program.Quote(LocalRoot));}}
        public static Dictionary<string,object> Preferences() {
            try{return Program.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(SharedDataRoot,"launcher-preferences.json"),Encoding.UTF8))??new Dictionary<string,object>();}catch{return new Dictionary<string,object>();}
        }
        static void RestorePreference(){
            var p=Preferences();object value;
            if(p.TryGetValue("workspace",out value)&&value is string)LocalRoot=(string)value;
            if(p.TryGetValue("mode",out value)&&Object.Equals(value,"local")){
                try{ResolveLocal();Local=true;}catch{Local=false;}
            }
        }
        public static void SavePreference(string source){
            Program.PrivateWrite(Path.Combine(SharedDataRoot,"launcher-preferences.json"),Program.Json.Serialize(new {mode=Local?"local":"online",workspace=LocalRoot,source=source}));
        }
        public static void Select(bool local,string workspace) {
            string old=LocalRoot;LocalRoot=workspace;
            try{if(local)ResolveLocal();}catch{LocalRoot=old;throw;}
            Local=local;Program.DataRoot=local?Path.Combine(LocalRoot,"state","unified-launcher"):SharedDataRoot;
        }
        static string Under(string root,string relative) {
            if(String.IsNullOrWhiteSpace(relative)||Path.IsPathRooted(relative))throw new IOException("Invalid local release path");
            string path=Path.GetFullPath(Path.Combine(root,relative.Replace('/',Path.DirectorySeparatorChar)));
            if(!path.StartsWith(Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Local path escaped");
            return path;
        }
        static string Hash(string file){using(var f=File.OpenRead(file))return Program.Hash(f);}
        public static string ResolveLocal() {
            var json=Program.Json;
            var pointer=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(LocalRoot,"releases","local","current.json"),Encoding.UTF8));
            object recovery;string rid=pointer.ContainsKey("release")?Convert.ToString(pointer["release"]):"";if((pointer.TryGetValue("recovery_only",out recovery)&&(!(recovery is bool)||(bool)recovery))||rid.StartsWith(NextAccessoryCohort.ManagedRelease+"-guarded-",StringComparison.Ordinal)||rid.StartsWith(NextOwnedStonesCohort.ManagedRelease+"-guarded-",StringComparison.Ordinal)||rid.StartsWith(NextCacheCohort.ManagedRelease+"-guarded-",StringComparison.Ordinal)||(!String.IsNullOrEmpty(LocalBootstrap.RepairManagedRelease)&&rid.StartsWith(LocalBootstrap.RepairManagedRelease+"-guarded-",StringComparison.Ordinal)))throw new IOException("Complete C3 compatible recovery is retained; normal LOCAL startup requires a separately qualified forward repair");
            if(Convert.ToString(pointer["channel"])!="local")throw new IOException("Wrong local channel");
            string root=Under(LocalRoot,Convert.ToString(pointer["path"]));
            if(!root.StartsWith(Path.Combine(LocalRoot,"releases","local")+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Wrong local release root");
            if(!File.Exists(Path.Combine(root,"release-snapshot.json"))||!File.Exists(Path.Combine(root,"els_server","application.py")))throw new IOException("Local release is incomplete");
            if(Hash(Path.Combine(root,"local-business-manifest.json"))!=Convert.ToString(pointer["manifest_sha256"]))throw new IOException("Local release manifest changed");
            return root;
        }
        public static string Prepare(Action<string> progress) {
            if(!Local)return Program.EnsurePayload(progress);
            string root=ResolveLocal();progress("正在检查本地运行组件…");VerifyLocalComponents(root);return root;
        }
        static void VerifyLocalComponents(string root,string expectedManifest=null) {
            var json=new System.Web.Script.Serialization.JavaScriptSerializer {MaxJsonLength=4*1024*1024};
            if(expectedManifest==null) {
                var pointer=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(LocalRoot,"releases","local","current.json"),Encoding.UTF8));
                object digest;if(!pointer.TryGetValue("runtime_manifest_sha256",out digest))throw new IOException("Local runtime manifest binding missing");
                expectedManifest=Convert.ToString(digest);
            }
            if(String.IsNullOrEmpty(expectedManifest)||Hash(Path.Combine(root,"client-bundle-manifest.json"))!=expectedManifest)throw new IOException("Local runtime manifest changed");
            var bundle=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(root,"client-bundle-manifest.json"),Encoding.UTF8));
            foreach(Dictionary<string,object> row in (IEnumerable)bundle["files"]) {
                string file=Under(root,Convert.ToString(row["path"]));
                if(!File.Exists(file)||new FileInfo(file).Length!=Convert.ToInt64(row["size"])||Hash(file)!=Convert.ToString(row["sha256"]))throw new IOException("Local component changed: "+row["path"]);
            }
        }
        public static Dictionary<string,object> VerifiedLocalIdentity(string root) {
            if(!String.Equals(System.IO.Path.GetFullPath(root),ResolveLocal(),StringComparison.OrdinalIgnoreCase))throw new IOException("LOCAL runtime is not the selected release");
            VerifyLocalComponents(root);
            return new Dictionary<string,object>{{"runtime_kind","local-release"},{"payload",null},{"runtime_release",Path.GetFileName(root)},{"runtime_manifest_sha256",Hash(Path.Combine(root,"client-bundle-manifest.json"))},{"local_business_manifest_sha256",Hash(Path.Combine(root,"local-business-manifest.json"))},{"runtime_identity_state","verified"}};
        }
        public static string ResolveDiagnosticLocal(Dictionary<string,object> identity) {
            string release=Convert.ToString(identity["runtime_release"]);
            if(String.IsNullOrEmpty(LocalRoot)||!System.Text.RegularExpressions.Regex.IsMatch(release??"","^[a-z0-9][a-z0-9-]{0,95}$"))throw new IOException("Invalid recorded LOCAL release");
            string root=Under(LocalRoot,"releases/local/"+release);
            if(Hash(Path.Combine(root,"local-business-manifest.json"))!=Convert.ToString(identity["local_business_manifest_sha256"])||Hash(Path.Combine(root,"client-bundle-manifest.json"))!=Convert.ToString(identity["runtime_manifest_sha256"]))throw new IOException("Recorded LOCAL runtime identity changed");
            VerifyLocalComponents(root,Convert.ToString(identity["runtime_manifest_sha256"]));return root;
        }
        public static string Arguments(string root,string client,string config) {
            return Program.Quote(Path.Combine(root,"tools","launch_client.py"))+" --client "+Program.Quote(client)+" --config "+Program.Quote(config)+" --allow-client-variants";
        }

    }
    partial class MainForm {
        void ConfigureLocal() {
            Text="艾尔之光 · 统一启动器";
            nameBox.ReadOnly=false;passwordBox.Enabled=true;remember.Enabled=true;
            login.Text="开始游戏";register.Text="第一次来？创建账号";recover.Text="恢复新手起点";
            remember.Text="记住登录和密码";
            LoadSaved();
            if(!LocalBootstrap.Installed(LaunchMode.LocalRoot)) {
                server.Text="正在准备本机服务器";Status("正在迁移到统一服务端，请稍候…");return;
            }
            var identity=UnifiedEndpoint.Credentials();
            string ownerName=Convert.ToString(identity["name"]);
            if((String.IsNullOrEmpty(nameBox.Text)||String.Equals(nameBox.Text,ownerName,StringComparison.Ordinal))
                &&String.IsNullOrEmpty(PasswordForAuth())&&(String.IsNullOrEmpty(token)||tokenName!=ownerName)) {
                nameBox.Text=ownerName;token=Convert.ToString(identity["token"]);tokenName=ownerName;
            }
            server.Text="本机服务器";
            Status("使用统一服务端，原有角色和存档已保留。");
        }
        async System.Threading.Tasks.Task<bool> PrepareLocalDeployment() {
            if(!LaunchMode.Local||LocalBootstrap.Current(LaunchMode.LocalRoot))return true;
            activeOperation=localChoice;SetBusy(true);
            try {
                string workspace=LaunchMode.LocalRoot;
                await System.Threading.Tasks.Task.Run(()=>UnifiedInstall.Run(workspace,(percent,message)=>{
                    if(!IsDisposed&&IsHandleCreated)BeginInvoke((Action)(()=>{journeyProgress.Value=percent;Status(message);}));
                }));
                ConfigureLocal();RefreshModeDesign();return true;
            }catch(Exception error){Status(error.Message,true);return false;}
            finally{SetBusy(false);}
        }
        public object LocalContractForTest() {
            if(!LaunchMode.Local||!passwordBox.Enabled||!remember.Enabled||nameBox.ReadOnly)throw new IOException("Unified account controls unavailable");
            string args=LaunchMode.Arguments(LaunchMode.ResolveLocal(),clientPath,"test-config.json");
            if(args.Contains("--mode local")||!args.Contains("--config"))throw new IOException("Unified launch arguments differ");
            return new {ok=true,same_entry="tools/launch_client.py",authenticated=true,server_host=Program.Host};
        }

    }
}
