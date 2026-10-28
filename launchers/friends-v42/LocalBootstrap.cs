using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;

namespace ElsFriends {
    static class LocalBootstrap {
        public const string PayloadHash = "70e06dca0f929d0f2bc053a5cb226b960bf7026c13ae10dda503f96f485aeec4";
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
        public static string Run(string repository,Action<int,string> progress) {
            repository=SourceUpdate.Validate(repository);
            string commit=SourceUpdate.CurrentCommit(repository),workspace=Workspace(repository);
            // Existing pointers are resolved by the normal mode path. Never overwrite one here.
            progress(5,"正在准备已签名的本地运行环境…");
            string runtime=ComponentRuntime.EnsureLocal(message=>progress(10,message));
            string folder=Path.Combine(LaunchMode.SharedDataRoot,"local-bootstrap",Guid.NewGuid().ToString("N"));Directory.CreateDirectory(folder);
            string script=Path.Combine(folder,"local_bootstrap.py"),manifest=Path.Combine(folder,"verified-runtime-files.json"),result=Path.Combine(folder,"result.json"),log=Path.Combine(folder,"bootstrap.log");
            string text;using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("ElsFriends.LocalBootstrap"))using(var reader=new StreamReader(stream,Encoding.UTF8))text=reader.ReadToEnd();
            Program.PrivateWrite(script,text);Program.PrivateWrite(manifest,ComponentRuntime.LocalFileManifest(runtime));
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
                process.Start();process.BeginOutputReadLine();process.BeginErrorReadLine();process.WaitForExit();
                if(!File.Exists(result))throw new IOException("本地初始化中断，原有存档保持。请重试；诊断："+log);
                var final=new System.Web.Script.Serialization.JavaScriptSerializer {MaxJsonLength=4*1024*1024}.Deserialize<Dictionary<string,object>>(File.ReadAllText(result,Encoding.UTF8));
                if(process.ExitCode!=0||!Program.Ok(final))throw new IOException(final.ContainsKey("error")?Convert.ToString(final["error"]):"本地初始化未完成，请查看诊断后重试。");
                if(!String.Equals(Path.GetFullPath(Convert.ToString(final["workspace"])),Path.GetFullPath(workspace),StringComparison.OrdinalIgnoreCase)||!Installed(workspace))throw new IOException("本地安装目录核验失败。");
                string old=LaunchMode.LocalRoot;try{LaunchMode.LocalRoot=workspace;LaunchMode.ResolveLocal();}finally{LaunchMode.LocalRoot=old;}
                progress(100,"本地版本已准备完成，请选择客户端并开始游戏。");return workspace;
            }
        }
    }
}
