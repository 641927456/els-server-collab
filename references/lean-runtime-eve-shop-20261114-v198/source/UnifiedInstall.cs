using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
namespace ElsFriends {
    static class UnifiedInstall {
        public static string Run(string workspace,Action<int,string> progress) {
            LeanRuntime.RequireServerDownload();
            progress(5,"正在准备统一服务端组件…");
            var modules=ComponentRuntime.EnsureLocalModules(message=>progress(20,message));return RunPrepared(workspace,modules,progress);
        }
        internal static string RunPrepared(string workspace,Tuple<string,string> modules,Action<int,string> progress) {
            string clientRoot=modules.Item1,root=modules.Item2;
            string area=Path.Combine(workspace,"state","unified-installer-requests",Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(area);
            string manifest=Path.Combine(area,"files.json"),result=Path.Combine(area,"result.json");
            Program.PrivateWrite(manifest,LeanRuntime.LocalManifest(clientRoot,root));
            string args="-B -X utf8 "+Program.Quote(Path.Combine(root,"tools","install_unified_runtime.py"))+" --client-root "+Program.Quote(clientRoot)+" --workspace "+Program.Quote(workspace)+" --manifest "+Program.Quote(manifest)+" --result "+Program.Quote(result);
            UnifiedEndpoint.StopOwnedForUpdate();
            var info=new ProcessStartInfo(Path.Combine(root,"server-python","python.exe"),args){UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden,WorkingDirectory=root,RedirectStandardOutput=true,RedirectStandardError=true};
            using(var process=Process.Start(info)) {
                var output=process.StandardOutput.ReadToEndAsync();var errors=process.StandardError.ReadToEndAsync();process.WaitForExit();
                File.WriteAllText(Path.Combine(area,"install.log"),output.Result+errors.Result,Encoding.UTF8);
                if(process.ExitCode!=0||!File.Exists(result))throw new IOException("统一服务端安装未完成，请查看本次安装日志。原有存档保持。");
                var doc=Program.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(result,Encoding.UTF8));
                if(!Program.Ok(doc))throw new IOException(Convert.ToString(doc["error"]));
            }
            progress(100,"统一服务端已准备，下一次正常启动生效。");return workspace;
        }
    }
}
