using System;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace ElsFriends {
    partial class MainForm {
        readonly Button localDownload=new SoftButton();
        string LocalDownloadWorkspace() {
            string existing=FindWorkspace();if(!String.IsNullOrEmpty(existing))return existing;
            if(!String.IsNullOrEmpty(LaunchMode.LocalSource))return LocalBootstrap.Workspace(SourceUpdate.Validate(LaunchMode.LocalSource));
            return Path.Combine(ClientStorage.Root,"local-server");
        }
        async Task DownloadLocalServer() {
            if(busy||checkingUpdate)return;
            if(!LocalSelection)return;
            if(!File.Exists(clientPath)){SetSettingsOpen(true);Status("请先选择客户端目录，本地服务端将下载到该目录。");return;}
            string workspace;
            try{ClientStorage.Activate(clientPath);ClientStorage.WritableRoot();workspace=LocalDownloadWorkspace();}catch(IOException error){Status(error.Message,true);return;}
            if(!proofMode&&!Save())return;
            activeOperation=localDownload;SetBusy(true);Status("正在下载本地服务端…");
            try {
                await Task.Run(()=>{
                    Action<int,string> progress=(percent,message)=>{if(!IsDisposed&&IsHandleCreated)BeginInvoke((Action)(()=>{if(busy){journeyProgress.Value=percent;Status(message);}}));};
                    var modules=ComponentRuntime.EnsureLocalModules(message=>progress(20,message));
                    UnifiedInstall.RunPrepared(workspace,modules,progress);
                });
                LaunchMode.LocalRoot=workspace;if(!proofMode)LaunchMode.SavePreference(sourceFolder);
                SetBusy(false);if(!LaunchMode.Local&&!SwitchMode(true,workspace))return;
                MotionEffects.Feedback(localDownload,true);
                Status("本地服务端已下载并准备好，可以开始本地游玩。");
            }catch(Exception error){Status(error is IOException?error.Message:"本地服务端下载未完成，请检查网络和目录后重试。",true);}
            finally{SetBusy(false);}
        }
    }
}
