using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Text;

namespace ElsFriends {
    // Server business code never selects a LOCAL implementation. The selected
    // target IP only determines whether this launcher owns a loopback service.
    static class UnifiedEndpoint {
        static Process owned;
        static string ownedRoot,ownedStop;
        static readonly object gate=new object();
        public static bool IsLoopback {get{IPAddress ip;return IPAddress.TryParse(Program.Host,out ip)&&IPAddress.IsLoopback(ip);}}
        static string Home {get{return Path.Combine(LaunchMode.LocalRoot,"state","unified-server");}}
        static Dictionary<string,object> Identity() {
            return Program.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(Home,"endpoint.json"),Encoding.UTF8));
        }
        public static string Pin {get{return Convert.ToString(Identity()["certificate_sha256"]);}}
        public static Dictionary<string,object> Credentials() {
            byte[] clear=ProtectedData.Unprotect(File.ReadAllBytes(Path.Combine(Home,"owner.dpapi")),Encoding.UTF8.GetBytes("ELS unified server owner v1"),DataProtectionScope.CurrentUser);
            try{return Program.Json.Deserialize<Dictionary<string,object>>(Encoding.UTF8.GetString(clear));}
            finally{Array.Clear(clear,0,clear.Length);}
        }
        static void StopOwnedLocked() {
            if(owned==null)return;
            if(!owned.HasExited) {
                File.WriteAllText(ownedStop,"launcher requested normal service update",Encoding.UTF8);
                if(!owned.WaitForExit(30000))throw new IOException("旧本机服务端尚未正常退出，更新未继续；请稍候重试。");
            }
            owned.Dispose();owned=null;ownedRoot=null;ownedStop=null;
        }
        public static void StopOwnedForUpdate() {lock(gate){StopOwnedLocked();}}
        public static void EnsureRunning() {
            if(!IsLoopback)return;
            lock(gate) {
                if(!LocalBootstrap.Current(LaunchMode.LocalRoot))throw new IOException("请先完成当前统一服务端安装。");
                string root=LaunchMode.ResolveLocal();
                if(owned!=null) {
                    if(owned.HasExited)throw new IOException("本机服务端已退出，请查看服务端日志。");
                    if(String.Equals(root,ownedRoot,StringComparison.OrdinalIgnoreCase))return;
                    StopOwnedLocked();
                }
                LaunchMode.VerifiedLocalIdentity(root);
                string ready=Path.Combine(Home,Guid.NewGuid().ToString("N")+".ready"),stop=ready+".stop";
                var owner=Process.GetCurrentProcess();
                string args=Program.Quote(Path.Combine(root,"tools","run_unified_server.py"))+" --config "+Program.Quote(Path.Combine(Home,"server.toml"))+" --ready "+Program.Quote(ready)+" --stop-file "+Program.Quote(stop)+" --owner-pid "+owner.Id+" --owner-created "+owner.StartTime.ToUniversalTime().ToFileTimeUtc();
                var serverStart=new ProcessStartInfo(Path.Combine(root,"server-python","python.exe"),"-B -X utf8 "+args){UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden,WorkingDirectory=root};
                serverStart.EnvironmentVariables["MIMALLOC_EAGER_COMMIT"]="0";
                owned=Process.Start(serverStart);
                ownedRoot=root;ownedStop=stop;
                var deadline=DateTime.UtcNow.AddSeconds(75);
                while(!File.Exists(ready)) {
                    if(owned.HasExited||DateTime.UtcNow>=deadline) {File.WriteAllText(stop,"launcher startup ended");throw new IOException("本机服务端启动未完成；已有游戏和服务保持原状。");}
                    System.Threading.Thread.Sleep(100);
                }
            }
        }
    }
}
