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
        public static readonly string SharedDataRoot=Program.DataRoot;
        public static string[] Parse(string[] args) {
            var rest=new List<string>();bool explicitMode=false;
            for(int i=0;i<args.Length;i++) {
                if(args[i]=="--local"){Local=true;explicitMode=true;}
                else if(args[i]=="--online"){Local=false;explicitMode=true;}
                else if(args[i]=="--local-root") {
                    if(++i>=args.Length||!Path.IsPathRooted(args[i]))throw new IOException("A local workspace is required");
                    LocalRoot=Path.GetFullPath(args[i]);
                } else rest.Add(args[i]);
            }
            if(!explicitMode&&(rest.Count==0||rest[0]=="--updated-parent"))RestorePreference();
            if(Local) {
                if(LocalRoot==null)throw new IOException("A local workspace is required");
                ResolveLocal();
                Program.DataRoot=Path.Combine(LocalRoot,"state","unified-launcher");
            }
            return rest.ToArray();
        }
        public static string RestartArguments {get{return Local?" --local --local-root "+Program.Quote(LocalRoot):" --online"+(String.IsNullOrEmpty(LocalRoot)?"":" --local-root "+Program.Quote(LocalRoot));}}
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
            if(Convert.ToString(pointer["channel"])!="local")throw new IOException("Wrong local channel");
            string root=Under(LocalRoot,Convert.ToString(pointer["path"]));
            if(!root.StartsWith(Path.Combine(LocalRoot,"releases","local")+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Wrong local release root");
            if(!File.Exists(Path.Combine(root,"release-snapshot.json"))||!File.Exists(Path.Combine(root,"els_server","application.py")))throw new IOException("Local release is incomplete");
            if(Hash(Path.Combine(root,"local-business-manifest.json"))!=Convert.ToString(pointer["manifest_sha256"]))throw new IOException("Local release manifest changed");
            return root;
        }
        public static string Prepare(Action<string> progress) {
            if(!Local)return Program.EnsurePayload(progress);
            string root=ResolveLocal();progress("正在检查本地运行组件…");
            var json=new System.Web.Script.Serialization.JavaScriptSerializer {MaxJsonLength=4*1024*1024};
            var bundle=json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(root,"client-bundle-manifest.json"),Encoding.UTF8));
            foreach(Dictionary<string,object> row in (IEnumerable)bundle["files"]) {
                string file=Under(root,Convert.ToString(row["path"]));
                if(!File.Exists(file)||new FileInfo(file).Length!=Convert.ToInt64(row["size"])||Hash(file)!=Convert.ToString(row["sha256"]))throw new IOException("Local component changed: "+row["path"]);
            }
            return root;
        }
        public static string Arguments(string root,string client,string config) {
            string args=Program.Quote(Path.Combine(root,"tools","launch_client.py"))+" --mode "+(Local?"local":"friends")+" --client "+Program.Quote(client);
            return Local?args:args+" --config "+Program.Quote(config)+" --allow-client-variants";
        }
        public static void OpenManager(string view) {
            string root=ResolveLocal();
            // The manager retains its existing GM transactions, not a second start route.
            string python=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"Programs","Python","Python313","pythonw.exe");
            if(!File.Exists(python))throw new IOException("The local GM Python runtime is missing");
            var info=new ProcessStartInfo(python,Program.Quote(Path.Combine(root,"tools","open_local_manager.py"))+" --workspace "+Program.Quote(LocalRoot)+" --view "+view){UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=root,WindowStyle=ProcessWindowStyle.Hidden};
            Process.Start(info);
        }
    }
    partial class MainForm {
        void ConfigureLocal() {
            Text="艾尔之光 · 单机 / 联网统一启动器";
            if(!proofMode){var settings=Program.LoadSettings();if(settings.ContainsKey("client"))clientPath=Convert.ToString(settings["client"]);}
            if(String.IsNullOrWhiteSpace(clientPath))clientPath="D:\\艾尔之光\\data\\x2_dx11.exe";pathBox.Text=Path.GetDirectoryName(clientPath);
            token=null;tokenName=null;rememberedPassword=null;passwordName=null;
            nameBox.Text="local";passwordBox.Clear();remember.Checked=false;
            nameBox.ReadOnly=true;passwordBox.Enabled=false;remember.Enabled=false;
            remember.Text="单机存档保存在本机，无需联网账号";
            login.Text="开始单机冒险";register.Text="管理角色与 GM";recover.Text="存档与备份";
            server.Text="单机模式 · 本地存档";
            Status("准备就绪。角色与进度保存在这台电脑。");
        }
        void OpenManager(string view) {try{LaunchMode.OpenManager(view);}catch{Status("无法打开单机管理工具，请查看本地环境。",true);}}
        public object LocalContractForTest() {
            if(!LaunchMode.Local||passwordBox.Enabled||remember.Enabled||!nameBox.ReadOnly||token!=null)throw new IOException("Local credentials were not isolated");
            string args=LaunchMode.Arguments(LaunchMode.ResolveLocal(),clientPath,null);
            if(!args.Contains("launch_client.py")||!args.Contains("--mode local")||args.Contains("--config"))throw new IOException("Local entry contract differs");
            return new {ok=true,same_native_form=true,same_launch_method="LoginAndStart",same_entry="tools/launch_client.py",mode="local",online_credentials_disabled=true,local_release=LaunchMode.ResolveLocal(),restart_arguments=LaunchMode.RestartArguments};
        }
    }
}
