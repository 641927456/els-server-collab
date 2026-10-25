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
            var g=e.Graphics;g.Clear(MotionClock.ParentColor(this));g.SmoothingMode=SmoothingMode.AntiAlias;
            float h=Math.Min(4,Height-1);if(Width<8||h<1)return;
            using(var p=new Pen(Color.FromArgb(230,237,242),h)){p.StartCap=p.EndCap=LineCap.Round;g.DrawLine(p,3,Height/2f,Width-3,Height/2f);}
            float fraction=value/100f,start=3,end=3+(Width-6)*fraction;
            if(active&&target==0){fraction=.24f;start=3+(Width-6)*(.76f*(MotionClock.Reduced?.5f:phase));end=start+(Width-6)*fraction;}
            if(end>start)using(var p=new Pen(failed?Theme.Coral:Theme.Cyan,h)){p.StartCap=p.EndCap=LineCap.Round;g.DrawLine(p,start,Height/2f,end,Height/2f);}
        }
    }
    partial class MainForm {
        Button localChoice=new SoftButton(),onlineChoice=new SoftButton(),sourceBrowse=new SoftButton(),sourcePull=new SoftButton();
        Label modeSubtitle=new Label(),sourcePathLabel=new Label(),sourceHint=new Label();
        JourneyProgress journeyProgress=new JourneyProgress();bool switchingMode;string sourceFolder;
        void BuildModeSelector(TableLayoutPanel form) {
            var modes=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=3,RowCount=1,Margin=new Padding(0,1,0,7)};
            modes.RowStyles.Add(new RowStyle(SizeType.Percent,100));modes.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));modes.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,8));modes.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));
            localChoice.Text="本地版本";localChoice.AccessibleName="选择本地版本";onlineChoice.Text="线上版本";onlineChoice.AccessibleName="选择线上版本";
            localChoice.Dock=onlineChoice.Dock=DockStyle.Fill;localChoice.Font=onlineChoice.Font=new Font(Font.FontFamily,9,FontStyle.Bold);
            localChoice.Click+=delegate{SwitchMode(true);};onlineChoice.Click+=delegate{SwitchMode(false);};modes.Controls.Add(localChoice,0,0);modes.Controls.Add(onlineChoice,2,0);form.Controls.Add(modes,0,3);
        }
        string FindWorkspace() {
            if(!String.IsNullOrEmpty(LaunchMode.LocalRoot))return LaunchMode.LocalRoot;
            object saved;var prefs=LaunchMode.Preferences();if(prefs.TryGetValue("workspace",out saved)&&saved is string&&Directory.Exists((string)saved))return (string)saved;
            for(var dir=new DirectoryInfo(Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location));dir!=null;dir=dir.Parent)
                if(File.Exists(Path.Combine(dir.FullName,"releases","local","current.json")))return dir.FullName;
            return null;
        }
        void RefreshModeDesign() {
            Text="艾尔之光 · 统一启动器";
            localChoice.BackColor=LaunchMode.Local?Theme.Cyan:Color.FromArgb(241,246,250);localChoice.ForeColor=LaunchMode.Local?Color.White:Theme.Muted;
            onlineChoice.BackColor=!LaunchMode.Local?Theme.Cyan:Color.FromArgb(241,246,250);onlineChoice.ForeColor=!LaunchMode.Local?Color.White:Theme.Muted;
            modeSubtitle.Text=LaunchMode.Local?"本机存档 · 单机探索，无需联网账号":"朋友服 · 登录账号，与朋友一起冒险";
            login.AccessibleName=LaunchMode.Local?"启动本地游戏":"登录并启动游戏";
            register.AccessibleName=LaunchMode.Local?"管理本地角色与 GM":"注册朋友服账号";recover.AccessibleName=LaunchMode.Local?"本地存档与备份":"恢复新手起点";
        }
        bool SwitchMode(bool local) {
            if(busy||local==LaunchMode.Local)return false;
            string workspace=FindWorkspace();
            if(local&&(workspace==null||!File.Exists(Path.Combine(workspace,"releases","local","current.json")))) {
                if(proofMode)return false;
                using(var dialog=new FolderBrowserDialog {Description="选择本地服务端工作目录（包含 releases/local/current.json）",ShowNewFolderButton=false}) {
                    if(dialog.ShowDialog(this)!=DialogResult.OK)return false;workspace=dialog.SelectedPath;
                }
            }
            try {
                // Resolve before touching the active profile or its credentials.
                bool previous=LaunchMode.Local;string previousRoot=LaunchMode.LocalRoot;
                LaunchMode.Select(local,workspace);LaunchMode.Select(previous,previousRoot);
                if(!proofMode&&!Save())return false;
                switchingMode=true;
                try {
                    LaunchMode.Select(local,workspace);token=null;tokenName=null;rememberedPassword=null;passwordName=null;
                    nameBox.Clear();passwordBox.Clear();nameBox.ReadOnly=false;nameBox.Enabled=passwordBox.Enabled=remember.Enabled=true;
                    remember.Checked=true;remember.Text="记住登录和密码";clientPath="";pathBox.Clear();
                    if(local)ConfigureLocal();else {login.Text="登录并开始冒险";register.Text="第一次来？创建账号";recover.Text="恢复新手起点";LoadSaved();server.Text="线上模式 · 朋友服";Status("已切换线上版本，请登录账号。");}
                    RefreshModeDesign();if(!proofMode)LaunchMode.SavePreference(sourceFolder);
                } finally {switchingMode=false;}
                return true;
            }catch(IOException error){Status(error.Message,true);return false;}
             catch{Status("暂时无法切换，请检查本地版本及目录权限。",true);return false;}
        }
        void BuildSourceCard(TableLayoutPanel left) {
            var card=new SoftPanel {Dock=DockStyle.Fill,Padding=new Padding(18,12,18,12),Margin=Padding.Empty};left.Controls.Add(card,0,2);
            var layout=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=2,RowCount=4,Margin=Padding.Empty};layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));layout.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,135));
            foreach(int h in new[]{29,30,42,31})layout.RowStyles.Add(new RowStyle(SizeType.Absolute,h));card.Controls.Add(layout);
            layout.Controls.Add(new Label {Text="本地服务端更新",Font=new Font(Font.FontFamily,11,FontStyle.Bold),ForeColor=Theme.Ink,Dock=DockStyle.Fill,Margin=Padding.Empty},0,0);
            var badge=new Label {Text="GIT  /  AUTO UPDATE",Font=new Font("Segoe UI",7.5f,FontStyle.Bold),ForeColor=Theme.Cyan,TextAlign=ContentAlignment.MiddleRight,Dock=DockStyle.Fill,Margin=Padding.Empty};layout.Controls.Add(badge,1,0);
            sourcePathLabel.Dock=DockStyle.Fill;sourcePathLabel.AutoEllipsis=true;sourcePathLabel.ForeColor=Theme.Muted;sourcePathLabel.Font=new Font(Font.FontFamily,8);sourcePathLabel.Margin=Padding.Empty;layout.SetColumnSpan(sourcePathLabel,2);layout.Controls.Add(sourcePathLabel,0,1);
            sourceBrowse.Text="选择源码目录";sourceBrowse.AccessibleName="选择服务端 Git 仓库目录";sourceBrowse.Dock=DockStyle.Fill;sourceBrowse.Margin=new Padding(0,0,10,0);sourceBrowse.ForeColor=Theme.Cyan;sourceBrowse.BackColor=Color.FromArgb(238,247,249);((SoftButton)sourceBrowse).Glyph="folder";sourceBrowse.Click+=ChooseSource;layout.Controls.Add(sourceBrowse,0,2);
            sourcePull.Text="一键更新服务端";sourcePull.AccessibleName="一键更新本地服务端，自动拉取检查备份安装";sourcePull.Dock=DockStyle.Fill;sourcePull.BackColor=Theme.Cyan;sourcePull.ForeColor=Color.White;sourcePull.Font=new Font(Font.FontFamily,8.5f,FontStyle.Bold);sourcePull.Click+=async delegate{await PullSource();};layout.Controls.Add(sourcePull,1,2);
            sourceHint.Text="自动拉取、检查、备份与安装 · 保留账号和存档";sourceHint.ForeColor=Theme.Muted;sourceHint.Font=new Font(Font.FontFamily,7.5f);sourceHint.Dock=DockStyle.Fill;sourceHint.TextAlign=ContentAlignment.BottomLeft;sourceHint.Margin=Padding.Empty;layout.Controls.Add(sourceHint,0,3);layout.SetColumnSpan(sourceHint,2);
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
            if(busy)return;if(String.IsNullOrEmpty(sourceFolder)){ChooseSource(this,EventArgs.Empty);if(String.IsNullOrEmpty(sourceFolder))return;}
            string workspace=FindWorkspace();
            if(workspace==null){Status("请先选择本地版本并指定本地工作目录。",true);return;}
            string selectedClient=clientPath;
            if(!File.Exists(selectedClient)){Status("请先选择客户端目录，更新器需要执行完整启动预检。",true);return;}
            activeOperation=sourcePull;SetBusy(true);Status("正在准备一键更新本地服务端…");
            try {
                Action<int,string> report=(percent,message)=>{if(!IsDisposed&&IsHandleCreated)BeginInvoke((Action)(()=>{journeyProgress.Value=percent;MotionEffects.Progress(sourcePull,percent);sourceHint.Text=message;Status(message);}));};
                object result=await Task.Run(()=>{
                    var pulled=SourceUpdate.Pull(sourceFolder,(percent,message)=>report(percent*25/100,message));
                    var doc=Program.Json.Deserialize<System.Collections.Generic.Dictionary<string,object>>(Program.Json.Serialize(pulled));
                    return LocalInstall.Run(workspace,sourceFolder,Convert.ToString(doc["after"]),selectedClient,report);
                });
                Program.PrivateWrite(Path.Combine(Program.DataRoot,"logs","last-source-update.json"),Program.Json.Serialize(result));
                MotionEffects.Feedback(sourcePull,true);
            }catch(Exception error){journeyProgress.Value=0;sourceHint.Text="更新未完成，详情见右侧提示。";Status(error is IOException?error.Message:"Git 无法运行，请先安装 Git 并检查仓库权限。",true);}
            finally{MotionEffects.Progress(sourcePull,-1);SetBusy(false);}
        }
        public object ModeContractForTest() {
            bool start=LaunchMode.Local;string originalRoot=LaunchMode.LocalRoot;
            PrepareLaunchSmoke();Show();Application.DoEvents();
            if(start) {onlineChoice.PerformClick();if(LaunchMode.Local||passwordBox.Enabled==false||nameBox.ReadOnly)throw new IOException("Online switch failed");}
            nameBox.Text="mode_fixture";passwordBox.Text="fixture-password-only";token="fixture-token-only";tokenName=nameBox.Text;rememberedPassword=passwordBox.Text;passwordName=nameBox.Text;
            localChoice.PerformClick();if(!LaunchMode.Local||passwordBox.Enabled||remember.Enabled||!nameBox.ReadOnly||token!=null)throw new IOException("Local isolation failed");
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
