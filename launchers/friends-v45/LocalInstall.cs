using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;

namespace ElsFriends {
    static class LocalInstall {
        internal const string RepairRawUpdaterHash="9b49b080cbd9728ed6049f3197c69fa16af66b6fd605899fb5ee6d71f73db0f3";
        public static object Run(string workspace,string repository,string commit,string client,Action<int,string> progress) {
            string prior=LaunchMode.LocalRoot,root;
            try{LaunchMode.LocalRoot=workspace;root=LaunchMode.ResolveLocal();}finally{LaunchMode.LocalRoot=prior;}
            string text=ComponentRuntime.VerifiedLocalResource("ElsFriends.RepairRawLocalUpdater",RepairRawUpdaterHash);
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
