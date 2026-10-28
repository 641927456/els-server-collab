using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;

namespace ElsFriends {
    // Pull a source checkout only. Promoted runtimes and saves are never copied.
    static class SourceUpdate {
        static readonly string NoHooks=Path.Combine(Path.GetTempPath(),"els-no-git-hooks-"+Guid.NewGuid().ToString("N"));
        static string Git(string root, params string[] args) {
            var info=new ProcessStartInfo("git", "-c core.hooksPath="+Program.Quote(NoHooks)+" "+String.Join(" ",args.Select(Program.Quote))) {
                WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,
                RedirectStandardOutput=true,RedirectStandardError=true,
                StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8
            };
            info.EnvironmentVariables["GIT_TERMINAL_PROMPT"]="0";
            info.EnvironmentVariables["GCM_INTERACTIVE"]="never";
            using(var process=Process.Start(info)) {
                var output=process.StandardOutput.ReadToEndAsync();var error=process.StandardError.ReadToEndAsync();
                if(!process.WaitForExit(120000)){process.Kill();process.WaitForExit();throw new IOException("Git 操作超时，请检查网络后重试。");}
                Task.WaitAll(output,error);
                if(process.ExitCode!=0)throw new IOException("Git 操作未完成。请检查仓库权限、网络和分支状态；未执行强制覆盖。");
                return output.Result.Trim();
            }
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
