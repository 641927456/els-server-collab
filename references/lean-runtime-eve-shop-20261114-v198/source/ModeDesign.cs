using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Reflection;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace ElsFriends {
    class JourneyProgress:Control,IMotion {
        float value,phase;int target;bool active,failed;
        public bool Alive {get{return !IsDisposed&&IsHandleCreated;}}
        public bool Active {get{return active;}set{active=value;if(value){target=0;this.value=0;MotionClock.Wake(this);}Invalidate();}}
        public bool Failed {get{return failed;}set{failed=value;Invalidate();}}
        public int Value {get{return target;}set{target=Math.Max(0,Math.Min(100,value));MotionClock.Wake(this);Invalidate();}}
        public JourneyProgress(){DoubleBuffered=true;TabStop=false;AccessibleName="操作进度";}
        public bool Step(float dt){value=MotionClock.Approach(value,target,dt);phase=(phase+dt*.6f)%1;Invalidate();return active||Math.Abs(value-target)>.01f;}
        protected override void Dispose(bool disposing){if(disposing)MotionClock.Forget(this);base.Dispose(disposing);}
        protected override void OnPaint(PaintEventArgs e){
            var g=e.Graphics;g.Clear(MotionClock.ParentColor(this));if(!active)return;g.SmoothingMode=SmoothingMode.AntiAlias;
            float h=Math.Min(4,Height-1);if(Width<8||h<1)return;
            using(var p=new Pen(Theme.Line,h)){p.StartCap=p.EndCap=LineCap.Round;g.DrawLine(p,3,Height/2f,Width-3,Height/2f);}
            float fraction=value/100f,start=3,end=3+(Width-6)*fraction;
            if(active&&target==0){fraction=.24f;start=3+(Width-6)*(.76f*(MotionClock.Reduced?.5f:phase));end=start+(Width-6)*fraction;}
            if(end>start)using(var p=new Pen(failed?Theme.Coral:Theme.Cyan,h)){p.StartCap=p.EndCap=LineCap.Round;g.DrawLine(p,start,Height/2f,end,Height/2f);}
        }
    }
    partial class MainForm {
        Button localChoice=new SoftButton(),onlineChoice=new SoftButton(),sourceBrowse=new SoftButton(),sourcePull=new SoftButton();
        Label modeSubtitle=new Label(),sourcePathLabel=new Label(),sourceHint=new Label();
        JourneyProgress journeyProgress=new JourneyProgress();bool switchingMode;string sourceFolder;bool? selectedLocal;
        TableLayoutPanel modePanel,homeLayout,launcherShell;
        bool LocalSelection {get{return selectedLocal??LaunchMode.Local;}}
        void RefreshLocalActions(){login.Enabled=register.Enabled=recover.Enabled=!busy&&(!LocalSelection||LaunchMode.Local);}
        void BuildModeSelector(TableLayoutPanel form) {
            var modes=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=3,RowCount=1,Margin=Padding.Empty};
            modes.RowStyles.Add(new RowStyle(SizeType.Percent,100));modes.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));modes.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,8));modes.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));
            localChoice.Text="本地游玩";localChoice.AccessibleName="选择本地模式";onlineChoice.Text="联网游玩";onlineChoice.AccessibleName="选择联网模式";
            localChoice.Dock=onlineChoice.Dock=DockStyle.Fill;localChoice.Font=onlineChoice.Font=new Font(Font.FontFamily,10);
            localChoice.Click+=async delegate{await RequestMode(true);};onlineChoice.Click+=async delegate{LaunchMode.LocalSource=null;await RequestMode(false);};modes.Controls.Add(localChoice,0,0);modes.Controls.Add(onlineChoice,2,0);var panel=modePanel=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=1,RowCount=3,Margin=Padding.Empty};
            panel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));panel.RowStyles.Add(new RowStyle(SizeType.Absolute,42));panel.RowStyles.Add(new RowStyle(SizeType.Absolute,6));panel.RowStyles.Add(new RowStyle(SizeType.Absolute,38));panel.Controls.Add(modes,0,0);
            localDownload.Text="下载本地服务端";localDownload.AccessibleName="下载本地服务端，联网游玩无需下载";localDownload.Dock=DockStyle.Fill;localDownload.Margin=Padding.Empty;
            localDownload.Font=new Font(Font.FontFamily,9.5f);localDownload.BackColor=Theme.Surface;localDownload.ForeColor=Theme.Cyan;((SoftButton)localDownload).Quiet=true;((SoftButton)localDownload).Glyph="download";
            launcherTips.SetToolTip(localDownload,"仅本地游玩需要，联网游玩无需下载。");localDownload.Click+=async delegate{await DownloadLocalServer();};panel.Controls.Add(localDownload,0,2);form.Controls.Add(panel,0,3);
        }
        string FindWorkspace() {
            if(!String.IsNullOrEmpty(LaunchMode.LocalRoot))return LaunchMode.LocalRoot;
            object saved;var prefs=LaunchMode.Preferences();if(prefs.TryGetValue("workspace",out saved)&&saved is string&&Directory.Exists((string)saved))return (string)saved;
            for(var dir=new DirectoryInfo(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location));dir!=null;dir=dir.Parent)
                if(File.Exists(Path.Combine(dir.FullName,"releases","local","current.json")))return dir.FullName;
            return null;
        }
        void RefreshModeDesign() {
            Text="艾尔之光 · 朋友服启动器";
            bool local=LocalSelection;localDownload.Visible=local;
            modePanel.RowStyles[1].Height=local?6:0;modePanel.RowStyles[2].Height=local?38:0;
            homeLayout.RowStyles[2].Height=local?132:94;launcherShell.RowStyles[2].Height=local?284:246;RefreshLocalActions();
            localChoice.BackColor=onlineChoice.BackColor=Theme.Surface;localChoice.ForeColor=local?Theme.Cyan:Theme.Muted;onlineChoice.ForeColor=!local?Theme.Cyan:Theme.Muted;
            ((SoftButton)localChoice).Quiet=((SoftButton)onlineChoice).Quiet=true;((SoftButton)localChoice).Selected=local;((SoftButton)onlineChoice).Selected=!local;localChoice.Invalidate();onlineChoice.Invalidate();
            modeSubtitle.Text=local?(LaunchMode.Local?"本机服务器":"本地服务端待下载"):"线上服务器";
            login.AccessibleName=LaunchMode.Local?"启动本地游戏":"登录并启动游戏";
            register.AccessibleName="创建账号";recover.AccessibleName="恢复新手起点";
        }
        async Task<bool> RequestMode(bool local,string requested=null) {
            if(busy||checkingUpdate)return false;selectedLocal=local;RefreshModeDesign();if(!local)return SwitchMode(false);
            if(!File.Exists(clientPath)){SetSettingsOpen(true);Status("请先选择客户端目录，再下载本地服务端。");return false;}
            try {
                ClientStorage.Activate(clientPath);ClientStorage.WritableRoot();
                activeOperation=localChoice;SetBusy(true);Status("正在检查本地服务端…");
                if(!await Task.Run(()=>LeanRuntime.ServerDownloaded)){Status("本地游玩需要先下载服务端，请点击下方“下载本地服务端”。");return false;}
                string workspace;
                if(requested==null)workspace=LocalDownloadWorkspace();
                else if(LocalBootstrap.LegacyInstalled(requested))workspace=requested;
                else workspace=LocalBootstrap.Workspace(SourceUpdate.Validate(requested));
                if(LocalBootstrap.Current(workspace)){SetBusy(false);return SwitchMode(true,workspace);}
                if(!proofMode&&!Save())return false;
                Status("正在准备本地服务端…");
                await Task.Run(()=>UnifiedInstall.Run(workspace,(percent,message)=>{if(!IsDisposed&&IsHandleCreated)BeginInvoke((Action)(()=>{journeyProgress.Value=percent;Status(message);}));}));
                SetBusy(false);return SwitchMode(true,workspace);
            }catch(Exception error){Status(error is IOException?error.Message:"本地服务端准备未完成，请检查目录后重试。",true);return false;}
            finally{if(busy)SetBusy(false);}
        }
        bool SwitchMode(bool local,string selectedWorkspace=null) {
            if(busy||checkingUpdate||local==LaunchMode.Local)return false;
            string workspace=selectedWorkspace??FindWorkspace();
            if(local&&!LocalBootstrap.Installed(workspace)){Status("请先选择 Git 仓库并完成本地初始化。",true);return false;}
            try {
                // Resolve before touching the active profile or its credentials.
                bool previous=LaunchMode.Local;string previousRoot=LaunchMode.LocalRoot;string previousClient=clientPath;
                if(local){LaunchMode.LocalRoot=workspace;try{LaunchMode.ResolveLocal();}finally{LaunchMode.LocalRoot=previousRoot;}}
                if(!proofMode&&!Save())return false;
                switchingMode=true;
                try {
                    LaunchMode.Select(local,workspace);if(local)LaunchMode.LocalSource=null;token=null;tokenName=null;rememberedPassword=null;passwordName=null;
                    nameBox.Clear();passwordBox.Clear();nameBox.ReadOnly=false;nameBox.Enabled=passwordBox.Enabled=remember.Enabled=true;
                    remember.Checked=true;remember.Text="记住登录和密码";clientPath=previousClient;pathBox.Text=Path.GetDirectoryName(clientPath);if(File.Exists(clientPath))ClientStorage.Activate(clientPath);
                    if(local)ConfigureLocal();else {login.Text="开始游戏";register.Text="第一次来？创建账号";recover.Text="恢复新手起点";LoadSaved();server.Text="线上模式 · 朋友服";Status("已切换线上版本，请登录账号。");}
                    if(String.IsNullOrEmpty(clientPath)&&File.Exists(previousClient)){clientPath=previousClient;pathBox.Text=Path.GetDirectoryName(clientPath);ClientStorage.Activate(clientPath);}
                    RefreshModeDesign();if(!proofMode){Save();LaunchMode.SavePreference(sourceFolder);}
                } finally {switchingMode=false;}
                if(!proofMode)RefreshSelectedServerStatus();
                return true;
            }catch(IOException error){Status(error.Message,true);return false;}
             catch{Status("暂时无法切换，请检查本地版本及目录权限。",true);return false;}
        }
        void BuildSourceCard(TableLayoutPanel left,int row) {
            var card=new Panel {Dock=DockStyle.Fill,Padding=new Padding(0,8,0,8),Margin=Padding.Empty,BackColor=Theme.Surface};left.Controls.Add(card,0,row);
            var layout=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=2,RowCount=4,Margin=Padding.Empty};layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,164));
            foreach(int h in new[]{32,36,44,38})layout.RowStyles.Add(new RowStyle(SizeType.Absolute,h));card.Controls.Add(layout);
            layout.Controls.Add(new Label {Text="本地服务端",Font=new Font(Font.FontFamily,11,FontStyle.Bold),ForeColor=Theme.Ink,Dock=DockStyle.Fill,Margin=Padding.Empty},0,0);
            var badge=new Label {Text="账号与存档独立保存",Font=new Font("Segoe UI",7.5f,FontStyle.Bold),ForeColor=Theme.Cyan,TextAlign=ContentAlignment.MiddleRight,Dock=DockStyle.Fill,Margin=Padding.Empty};layout.Controls.Add(badge,1,0);
            sourcePathLabel.Dock=DockStyle.Fill;sourcePathLabel.AutoEllipsis=true;sourcePathLabel.ForeColor=Theme.Muted;sourcePathLabel.Font=new Font(Font.FontFamily,9);sourcePathLabel.Margin=Padding.Empty;layout.SetColumnSpan(sourcePathLabel,2);layout.Controls.Add(sourcePathLabel,0,1);
            sourceBrowse.Text="选择源码目录";sourceBrowse.AccessibleName="选择服务端 Git 仓库目录";sourceBrowse.Dock=DockStyle.Fill;sourceBrowse.Margin=new Padding(0,0,10,0);sourceBrowse.ForeColor=Theme.Cyan;sourceBrowse.BackColor=Theme.Field;((SoftButton)sourceBrowse).Glyph="folder";sourceBrowse.Click+=ChooseSource;layout.Controls.Add(sourceBrowse,0,2);
            sourcePull.Text="更新本地服务端";sourcePull.AccessibleName="一键更新本地服务端，自动拉取检查备份安装";sourcePull.Dock=DockStyle.Fill;sourcePull.BackColor=Theme.Primary;sourcePull.ForeColor=Color.White;sourcePull.Font=new Font(Font.FontFamily,8.5f,FontStyle.Bold);sourcePull.Click+=async delegate{await PullSource();};layout.Controls.Add(sourcePull,1,2);
            sourceHint.Text="更新统一版本 · 保留账号和存档";sourceHint.ForeColor=Theme.Muted;sourceHint.Font=new Font(Font.FontFamily,9);sourceHint.Dock=DockStyle.Fill;sourceHint.TextAlign=ContentAlignment.BottomLeft;sourceHint.Margin=Padding.Empty;layout.Controls.Add(sourceHint,0,3);layout.SetColumnSpan(sourceHint,2);
            if(!proofMode){object source;if(LaunchMode.Preferences().TryGetValue("source",out source)&&source is string)sourceFolder=(string)source;}
            if(String.IsNullOrEmpty(sourceFolder)){string workspace=FindWorkspace();if(workspace!=null&&Directory.Exists(Path.Combine(workspace,"collaboration","els-server-collab",".git")))sourceFolder=Path.Combine(workspace,"collaboration","els-server-collab");}
            sourcePathLabel.Text=String.IsNullOrEmpty(sourceFolder)?"选择已有服务端 Git 仓库，沿当前分支更新":sourceFolder;
        }
        void ChooseSource(object sender,EventArgs e) {
            using(var dialog=new FolderBrowserDialog {Description="选择已有服务端 Git 仓库根目录",ShowNewFolderButton=false}) {
                if(Directory.Exists(sourceFolder))dialog.SelectedPath=sourceFolder;
                if(dialog.ShowDialog(this)!=DialogResult.OK)return;
                try{string selected=SourceUpdate.Validate(dialog.SelectedPath);string branch=SourceUpdate.Describe(selected);sourceFolder=selected;sourcePathLabel.Text=selected;LaunchMode.SavePreference(sourceFolder);Status("源码分支："+branch+"。点击拉取后沿此分支上游快进更新。");}catch(Exception error){Status(error.Message,true);}
            }
        }
        async Task PullSource() {
            if(busy)return;string workspace=FindWorkspace();
            if(workspace==null){Status("请先选择本地安装目录。",true);return;}
            activeOperation=sourcePull;SetBusy(true);Status("正在更新统一服务端…");
            try {
                Action<int,string> report=(percent,message)=>{if(!IsDisposed&&IsHandleCreated)BeginInvoke((Action)(()=>{journeyProgress.Value=percent;sourceHint.Text=message;Status(message);}));};
                await Task.Run(()=>UnifiedInstall.Run(workspace,report));
                MotionEffects.Feedback(sourcePull,true);
            }catch(Exception error){Status(error.Message,true);}
            finally{MotionEffects.Progress(sourcePull,-1);SetBusy(false);}
        }
        public object ModeContractForTest() {
            bool start=LaunchMode.Local;string originalRoot=LaunchMode.LocalRoot;
            PrepareLaunchSmoke();Show();Application.DoEvents();
            if(start) {onlineChoice.PerformClick();if(LaunchMode.Local||passwordBox.Enabled==false||nameBox.ReadOnly)throw new IOException("Online switch failed");}
            nameBox.Text="mode_fixture";passwordBox.Text="fixture-password-only";token="example_only";tokenName=nameBox.Text;rememberedPassword=passwordBox.Text;passwordName=nameBox.Text;
            localChoice.PerformClick();if(!LaunchMode.Local||!passwordBox.Enabled||!remember.Enabled||nameBox.ReadOnly)throw new IOException("Unified local controls failed");
            var local=LocalContractForTest();
            onlineChoice.PerformClick();if(LaunchMode.Local||!passwordBox.Enabled||nameBox.ReadOnly||passwordBox.Text.Length!=0||token!=null)throw new IOException("Credentials crossed modes");
            SetBusy(true);localChoice.PerformClick();if(LaunchMode.Local||localChoice.Enabled||sourcePull.Enabled)throw new IOException("Busy controls active");SetBusy(false);
            if(start){localChoice.PerformClick();if(!LaunchMode.Local)throw new IOException("Restore local failed");}Hide();
            return new {ok=true,local=local,mode_buttons_use_real_callbacks=true,online_local_online=true,credentials_isolated=true,busy_switch_blocked=true,source_update_blocked_while_busy=true,no_game_started=true};
        }
        public object SourceButtonForTest(string folder) {
            if(!String.IsNullOrEmpty(Environment.GetEnvironmentVariable("ELS_UPDATER_FIXTURE_CLIENT")))clientPath=Environment.GetEnvironmentVariable("ELS_UPDATER_FIXTURE_CLIENT");
            sourceFolder=folder;PrepareLaunchSmoke();Show();Application.DoEvents();sourcePull.PerformClick();
            var deadline=DateTime.UtcNow.AddMinutes(12);
            while(busy&&DateTime.UtcNow<deadline){Application.DoEvents();System.Threading.Thread.Sleep(10);}
            Application.DoEvents();
            var chain=new System.Collections.Generic.List<object>();for(Control c=localChoice;c!=null;c=c.Parent)chain.Add(new {type=c.GetType().Name,enabled=c.Enabled,disposed=c.IsDisposed});
            Program.PrivateWrite(Path.Combine(Program.DataRoot,"source-button-observed.json"),Program.Json.Serialize(new {busy=busy,failed=journeyProgress.Failed,progress=journeyProgress.Value,pull_enabled=sourcePull.Enabled,mode_enabled=localChoice.Enabled,feedback=feedback.Text,chain=chain}));
            if(busy||journeyProgress.Failed||journeyProgress.Value!=100||!sourcePull.Enabled||!localChoice.Enabled)throw new IOException("Source button callback failed");
            Hide();return new {ok=true,native_button_perform_click=true,async_callback_completed=true,progress=journeyProgress.Value,buttons_restored=true,no_game_started=true};
        }
    }
}
