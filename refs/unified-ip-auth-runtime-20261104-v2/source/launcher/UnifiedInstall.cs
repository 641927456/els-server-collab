using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
namespace ElsFriends {
    static class UnifiedInstall {
        public static string Run(string workspace,Action<int,string> progress) {
            progress(5,"正在准备统一服务端组件…");
            string root=Program.EnsurePayload(message=>progress(20,message));
            string area=Path.Combine(workspace,"state","unified-installer-requests",Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(area);
            string manifest=Path.Combine(area,"files.json"),result=Path.Combine(area,"result.json");
            Program.PrivateWrite(manifest,ComponentRuntime.PreparedFiles(root));
            string args="-B -X utf8 "+Program.Quote(Path.Combine(root,"tools","install_unified_runtime.py"))+" --workspace "+Program.Quote(workspace)+" --manifest "+Program.Quote(manifest)+" --result "+Program.Quote(result);
            UnifiedEndpoint.StopOwnedForUpdate();
            var info=new ProcessStartInfo(Path.Combine(root,"python","python.exe"),args){UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden,WorkingDirectory=root,RedirectStandardOutput=true,RedirectStandardError=true};
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
