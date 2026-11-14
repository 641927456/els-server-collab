using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

namespace ElsFriends {
    static class LauncherArt {
        public static Image Load(string name){using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("ElsFriends."+name))using(var source=Image.FromStream(stream))return new Bitmap(source);}
    }
    class Wordmark:Control {
        readonly Image logo=LauncherArt.Load("Logo");
        public Wordmark(){DoubleBuffered=true;BackColor=Theme.Canvas;}
        protected override void OnPaintBackground(PaintEventArgs e){MotionClock.PaintParent(this,e.Graphics);}
        protected override void Dispose(bool disposing){if(disposing)logo.Dispose();base.Dispose(disposing);}
        protected override void OnPaint(PaintEventArgs e){e.Graphics.InterpolationMode=InterpolationMode.HighQualityBicubic;e.Graphics.DrawImage(logo,new RectangleF(0,1,110,37));using(var f=new Font("Microsoft YaHei UI",9))TextRenderer.DrawText(e.Graphics,"朋友服启动器",f,new Rectangle(122,0,120,Height),Theme.Muted,TextFormatFlags.VerticalCenter|TextFormatFlags.NoPadding);}
    }
    class AdventureScene:Panel {
        readonly Image art=LauncherArt.Load("Hero"),logo=LauncherArt.Load("Logo");
        public int TopBleed;
        public AdventureScene(){DoubleBuffered=true;}
        protected override void Dispose(bool disposing){if(disposing){art.Dispose();logo.Dispose();}base.Dispose(disposing);}
        public Bitmap CaptureBackdrop(Control panel){
            var bitmap=new Bitmap(panel.Width,panel.Height);var scenePosition=InForm(this);var panelPosition=InForm(panel);
            using(var g=Graphics.FromImage(bitmap)){g.Clear(Theme.Canvas);g.TranslateTransform(scenePosition.X-panelPosition.X,scenePosition.Y-panelPosition.Y);g.SetClip(new Rectangle(0,-TopBleed,Width,Height+TopBleed));RenderScene(g);}return bitmap;
        }
        static Point InForm(Control control){var point=Point.Empty;for(var current=control;current!=null&&!(current is Form);current=current.Parent)point.Offset(current.Left,current.Top);return point;}
        protected override void OnPaintBackground(PaintEventArgs e){RenderScene(e.Graphics);}
        void RenderScene(Graphics g){
            g.Clear(Theme.Canvas);g.InterpolationMode=InterpolationMode.HighQualityBicubic;float scale=Math.Max(Width/(float)art.Width,Height/(float)art.Height);
            g.DrawImage(art,new RectangleF((Width-art.Width*scale)/2,Math.Min(-TopBleed,(Height-art.Height*scale)*.28f),art.Width*scale,art.Height*scale));
            var fade=new Rectangle(0,Math.Max(0,Height-180),Width,180);using(var shade=new LinearGradientBrush(fade,Color.FromArgb(0,Theme.Canvas),Theme.Canvas,90f)){shade.WrapMode=WrapMode.TileFlipXY;g.FillRectangle(shade,fade);}
            // Bind the wordmark to the character and cape, as in the supplied launcher reference.
            g.DrawImage(logo,new RectangleF(Width*.385f,Height*.34f,326,121));
        }
    }
    class DownloadCard:SoftButton {
        readonly Image image=LauncherArt.Load("DownloadArt");
        public DownloadCard(){Text="客户端下载";AccessibleName="客户端下载，提取码 jrg6";BackColor=Theme.Surface;ForeColor=Color.White;}
        protected override void Dispose(bool disposing){if(disposing)image.Dispose();base.Dispose(disposing);}
        protected override void PaintContent(Graphics g,Rectangle area,Color ink,float hover){
            var rect=new Rectangle(area.X+2,area.Y+2,area.Width-4,area.Height-4);using(var clip=Theme.Round(rect,7)){
                var saved=g.Save();g.SetClip(clip);float scale=Math.Max(rect.Width/(float)image.Width,rect.Height/(float)image.Height);
                g.InterpolationMode=InterpolationMode.HighQualityBicubic;g.DrawImage(image,new RectangleF(rect.X+(rect.Width-image.Width*scale)/2,rect.Y+(rect.Height-image.Height*scale)/2,image.Width*scale,image.Height*scale));
                using(var shade=new LinearGradientBrush(rect,Color.FromArgb(58,10,18,48),Color.FromArgb(0,10,18,48),0f))g.FillRectangle(shade,rect);
                if(!Enabled)using(var dim=new SolidBrush(Color.FromArgb(145,Theme.Canvas)))g.FillRectangle(dim,rect);
                if(hover>0)using(var light=new SolidBrush(Color.FromArgb((int)(15*hover),Color.White)))g.FillRectangle(light,rect);
                using(var f=new Font("Microsoft YaHei UI",22,FontStyle.Bold))TextRenderer.DrawText(g,"客户端下载",f,new Rectangle(rect.X+22,rect.Y+24,rect.Width-36,43),Color.White,TextFormatFlags.NoPadding);
                using(var f=new Font("Microsoft YaHei UI",9.5f))TextRenderer.DrawText(g,"完整客户端 · 提取码 jrg6",f,new Rectangle(rect.X+24,rect.Y+76,rect.Width-36,25),Color.FromArgb(223,231,255),TextFormatFlags.NoPadding);
                Glyphs.Draw(g,"download",new RectangleF(rect.X+25,rect.Bottom-40,18,18),Color.White,1.5f);
                using(var f=new Font("Microsoft YaHei UI",9))TextRenderer.DrawText(g,"获取客户端",f,new Rectangle(rect.X+52,rect.Bottom-41,150,24),Color.White,TextFormatFlags.NoPadding);
                g.Restore(saved);
            }
        }
    }
    partial class MainForm {
        Button activeOperation;
        Panel launcherSettings,accountPanel;
        AdventureScene heroScene;
        GlassPanel headerGlass;
        FlatInfoPanel information;
        SoftButton settingsToggle,clientSummary,accountSummary,accountContinue;
        readonly ToolTip launcherTips=new ToolTip();
        static TableLayoutPanel Grid(int columns,int rows){return new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=columns,RowCount=rows,Margin=Padding.Empty,Padding=Padding.Empty,BackColor=Color.Transparent};}
        static Label Caption(string text,float size=10){return new Label {Text=text,Dock=DockStyle.Fill,Margin=Padding.Empty,BackColor=Color.Transparent,ForeColor=Theme.Muted,Font=new Font("Microsoft YaHei UI",size),TextAlign=ContentAlignment.MiddleLeft};}
        SoftButton LinkButton(string text,string glyph,Action action){var b=new SoftButton {Text=text,Glyph=glyph,Quiet=true,Compact=true,Dock=DockStyle.Fill,BackColor=Theme.Canvas,ForeColor=Theme.Muted,Font=new Font(Font.FontFamily,10),AccessibleName=text};b.Click+=delegate{action();};return b;}
        SoftButton IconButton(string label,string glyph,Action action){var b=LinkButton("",glyph,action);b.AccessibleName=label;launcherTips.SetToolTip(b,label);return b;}
        void BuildDesign(){
            Disposed+=delegate{launcherTips.Dispose();};
            var shell=launcherShell=Grid(1,4);shell.RowStyles.Add(new RowStyle(SizeType.Absolute,40));shell.RowStyles.Add(new RowStyle(SizeType.Percent,100));shell.RowStyles.Add(new RowStyle(SizeType.Absolute,284));shell.RowStyles.Add(new RowStyle(SizeType.Absolute,72));Controls.Add(shell);
            heroScene=new AdventureScene {Dock=DockStyle.Fill,Margin=Padding.Empty,TopBleed=40};
            headerGlass=new GlassPanel(heroScene,true) {Dock=DockStyle.Fill,Margin=Padding.Empty,AccessibleName="半透明标题栏"};shell.Controls.Add(headerGlass,0,0);
            var top=Grid(4,1);headerGlass.Controls.Add(top);top.TabIndex=9;top.Padding=new Padding(28,1,16,1);top.RowStyles.Add(new RowStyle(SizeType.Percent,100));top.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,260));top.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));top.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,180));top.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,111));
            var wordmark=new Wordmark {Dock=DockStyle.Fill,Margin=Padding.Empty};top.Controls.Add(wordmark,0,0);
            server.Font=new Font(Font.FontFamily,9);server.Dock=DockStyle.Fill;server.ForeColor=Theme.Muted;server.TextAlign=ContentAlignment.MiddleRight;server.Margin=new Padding(0,0,16,0);top.Controls.Add(server,1,0);
            update.Text="V"+AutoUpdate.Version+"  检查更新";update.Dock=DockStyle.Fill;update.BackColor=Theme.Canvas;update.ForeColor=Theme.Muted;update.Font=new Font(Font.FontFamily,9);update.Margin=new Padding(0,2,10,2);update.AccessibleName="检查启动器更新";((SoftButton)update).Glyph="refresh";((SoftButton)update).Quiet=true;((SoftButton)update).Compact=true;
            update.Click+=async delegate{if(readyUpdate!=null){if(busy){Status("请正常退出游戏后，再更新启动器。");return;}AutoUpdate.PendingLauncher=readyUpdate;Close();}else await CheckUpdate(true);};top.Controls.Add(update,2,0);
            var controls=WindowControls(true);controls.Margin=new Padding(0,4,0,0);top.Controls.Add(controls,3,0);GlassPanel.TransparentChildren(headerGlass);BindWindowDrag(headerGlass);BindWindowDrag(top);BindWindowDrag(wordmark);BindWindowDrag(server);
            shell.Controls.Add(heroScene,0,1);
            var body=Grid(3,1);body.TabIndex=0;body.Padding=new Padding(42,8,42,10);body.RowStyles.Add(new RowStyle(SizeType.Percent,100));body.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,368));body.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,32));body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));shell.Controls.Add(body,0,2);
            var download=new DownloadCard {Dock=DockStyle.Fill,Margin=Padding.Empty,TabIndex=2};download.Click+=delegate{OpenExternal(AutoUpdate.ClientUrl);};body.Controls.Add(download,0,0);
            var home=homeLayout=Grid(1,5);home.TabIndex=0;foreach(int h in new[]{84,8,132,34,4})home.RowStyles.Add(new RowStyle(SizeType.Absolute,h));body.Controls.Add(home,2,0);
            var heading=Grid(4,1);heading.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));heading.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,222));heading.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,10));heading.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,58));heading.RowStyles.Add(new RowStyle(SizeType.Percent,100));home.Controls.Add(heading,0,0);
            var game=Grid(1,2);game.TabIndex=2;game.RowStyles.Add(new RowStyle(SizeType.Absolute,48));game.RowStyles.Add(new RowStyle(SizeType.Absolute,36));heading.Controls.Add(game,0,0);
            game.Controls.Add(new Label {Text="艾尔之光",Dock=DockStyle.Fill,ForeColor=Theme.Ink,Font=new Font(Font.FontFamily,28,FontStyle.Bold),Margin=Padding.Empty},0,0);
            var shortcuts=Grid(2,1);shortcuts.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,36));shortcuts.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));shortcuts.RowStyles.Add(new RowStyle(SizeType.Percent,100));game.Controls.Add(shortcuts,0,1);
            shortcuts.Controls.Add(IconButton("查看项目进度","progress",()=>OpenExternal(AutoUpdate.ProgressUrl)),0,0);
            modeSubtitle.Dock=DockStyle.Fill;modeSubtitle.ForeColor=Theme.Muted;modeSubtitle.Font=new Font(Font.FontFamily,9.5f);modeSubtitle.TextAlign=ContentAlignment.MiddleLeft;modeSubtitle.Margin=new Padding(10,0,0,0);shortcuts.Controls.Add(modeSubtitle,1,0);
            var launch=Grid(1,2);launch.TabIndex=1;launch.RowStyles.Add(new RowStyle(SizeType.Absolute,64));launch.RowStyles.Add(new RowStyle(SizeType.Absolute,20));heading.Controls.Add(launch,1,0);
            login.Text="开始游戏";login.Dock=DockStyle.Fill;login.BackColor=Theme.Primary;login.ForeColor=Color.White;login.Font=new Font(Font.FontFamily,15,FontStyle.Bold);login.AccessibleName="登录并启动游戏";((SoftButton)login).Glyph="play";((SoftButton)login).Gradient=true;login.Click+=async delegate{activeOperation=login;await LoginAndStart();};launch.Controls.Add(login,0,0);
            var renderer=Caption("DirectX 11  /  64 位",9);renderer.TextAlign=ContentAlignment.MiddleCenter;launch.Controls.Add(renderer,0,1);
            settingsToggle=IconButton("设置与帮助","settings",ToggleLauncherSettings);settingsToggle.BackColor=Theme.Surface;settingsToggle.Quiet=false;settingsToggle.Margin=new Padding(0,0,0,20);heading.Controls.Add(settingsToggle,3,0);
            information=new FlatInfoPanel {Dock=DockStyle.Fill,Margin=Padding.Empty};home.Controls.Add(information,0,2);var cells=Grid(5,1);for(int i=0;i<5;i++)cells.ColumnStyles.Add(new ColumnStyle(i%2==0?SizeType.Percent:SizeType.Absolute,i%2==0?100f/3:1));cells.RowStyles.Add(new RowStyle(SizeType.Percent,100));information.Controls.Add(cells);for(int i=1;i<5;i+=2)cells.Controls.Add(new Panel {Name="material-separator",Dock=DockStyle.Fill,BackColor=Theme.Line,Margin=new Padding(0,19,0,19)},i,0);
            GlassPanel.TransparentChildren(information);var mode=InfoCell("游玩模式");cells.Controls.Add(mode,0,0);var modes=Grid(1,4);for(int i=0;i<3;i++)modes.RowStyles.Add(new RowStyle(SizeType.Absolute,0));modes.RowStyles.Add(new RowStyle(SizeType.Percent,100));mode.Controls.Add(modes,0,1);BuildModeSelector(modes);
            var client=InfoCell("客户端");cells.Controls.Add(client,2,0);clientSummary=LinkButton("选择客户端","folder",()=>SetSettingsOpen(true));clientSummary.TextAlign=ContentAlignment.MiddleLeft;clientSummary.BackColor=Theme.Surface;client.Controls.Add(clientSummary,0,1);
            var account=InfoCell("账号");cells.Controls.Add(account,4,0);accountSummary=LinkButton("登录账号","user",()=>SetAccountOpen(true));accountSummary.TextAlign=ContentAlignment.MiddleLeft;accountSummary.BackColor=Theme.Surface;account.Controls.Add(accountSummary,0,1);GlassPanel.TransparentChildren(information);
            feedback.Text="选择客户端并登录后，即可开始游戏。";feedback.Dock=DockStyle.Fill;feedback.ForeColor=Theme.Muted;feedback.Font=new Font(Font.FontFamily,9.5f);feedback.TextAlign=ContentAlignment.MiddleLeft;feedback.Margin=new Padding(0,1,0,0);home.Controls.Add(feedback,0,3);journeyProgress.Dock=DockStyle.Fill;journeyProgress.Margin=Padding.Empty;home.Controls.Add(journeyProgress,0,4);
            var footer=Grid(3,1);footer.Padding=new Padding(42,8,42,10);footer.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,232));footer.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,24));footer.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));footer.RowStyles.Add(new RowStyle(SizeType.Percent,100));shell.Controls.Add(footer,0,3);
            var discord=new SoftButton {Name="discord-community",Text="加入 DC 交流频道",Glyph="discord",Dock=DockStyle.Fill,BackColor=Color.FromArgb(88,101,242),ForeColor=Color.White,Font=new Font(Font.FontFamily,11,FontStyle.Bold),AccessibleName="加入 DC 交流频道，在浏览器中打开 Discord 邀请"};discord.Click+=delegate{OpenExternal(DiscordInviteUrl);};footer.Controls.Add(discord,0,0);
            var notice=Caption(ProjectNotice,10);notice.Name="project-notice";notice.AccessibleName=ProjectNotice;notice.TextAlign=ContentAlignment.MiddleLeft;footer.Controls.Add(notice,2,0);
            BuildLauncherSettings();BuildAccountPanel();nameBox.TextChanged+=delegate{RefreshHomeSummary();};pathBox.TextChanged+=delegate{RefreshHomeSummary();};RefreshHomeSummary();
            KeyPreview=true;KeyDown+=delegate(object sender,KeyEventArgs e){if(e.KeyCode==Keys.Escape&&(accountPanel.Visible||launcherSettings.Visible)){if(accountPanel.Visible)SetAccountOpen(false);else SetSettingsOpen(false);e.Handled=true;e.SuppressKeyPress=true;}};
        }
        TableLayoutPanel InfoCell(string title){var cell=Grid(1,2);cell.Padding=new Padding(15,12,15,10);cell.BackColor=Theme.Surface;cell.RowStyles.Add(new RowStyle(SizeType.Absolute,24));cell.RowStyles.Add(new RowStyle(SizeType.Percent,100));cell.Controls.Add(Caption(title,9),0,0);return cell;}
        void RefreshHomeSummary(){clientSummary.Text=String.IsNullOrWhiteSpace(pathBox.Text)?"选择客户端":pathBox.Text;accountSummary.Text=String.IsNullOrWhiteSpace(nameBox.Text)?"登录账号":nameBox.Text;launcherTips.SetToolTip(clientSummary,String.IsNullOrWhiteSpace(pathBox.Text)?"选择已有客户端的目录":pathBox.Text);}
        void BuildLauncherSettings(){
            launcherSettings=new GlassPanel(heroScene) {Visible=false,Size=new Size(520,414),Padding=new Padding(22,16,22,16),BackColor=Theme.Surface,AccessibleName="启动器设置与帮助"};Controls.Add(launcherSettings);
            var layout=Grid(1,7);foreach(int h in new[]{44,8,24,48,14})layout.RowStyles.Add(new RowStyle(SizeType.Absolute,h));layout.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.RowStyles.Add(new RowStyle(SizeType.Absolute,48));launcherSettings.Controls.Add(layout);
            layout.Controls.Add(PanelHeading("设置与帮助",()=>SetSettingsOpen(false)),0,0);layout.Controls.Add(Caption("客户端目录"),0,2);
            var file=Grid(2,1);file.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));file.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,98));file.RowStyles.Add(new RowStyle(SizeType.Percent,100));layout.Controls.Add(file,0,3);
            pathBox.ReadOnly=true;pathBox.AccessibleName="客户端目录";pathBox.TabStop=false;file.Controls.Add(new MotionInput(pathBox,"folder"){Dock=DockStyle.Fill,Margin=new Padding(0,0,8,0),Placeholder="未选择客户端目录"},0,0);pathBox.Font=new Font(Font.FontFamily,9);
            browse.Text="选择目录";browse.Dock=DockStyle.Fill;browse.BackColor=Theme.Field;browse.ForeColor=Theme.Ink;browse.Font=new Font(Font.FontFamily,9.5f);browse.AccessibleName="选择客户端目录";browse.Click+=ChooseClient;file.Controls.Add(browse,1,0);BuildSourceCard(layout,5);
            var help=Grid(3,1);help.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));help.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,14));help.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));help.RowStyles.Add(new RowStyle(SizeType.Percent,100));help.Margin=new Padding(0,6,0,0);layout.Controls.Add(help,0,6);
            diagnostics.Text="诊断与反馈";diagnostics.Dock=DockStyle.Fill;diagnostics.BackColor=Theme.Surface;diagnostics.ForeColor=Theme.Muted;diagnostics.Font=new Font(Font.FontFamily,9.5f);diagnostics.AccessibleName="生成或上传诊断报告";((SoftButton)diagnostics).Glyph="help";((SoftButton)diagnostics).Quiet=true;diagnostics.Click+=async delegate{await OpenDiagnostics();};help.Controls.Add(diagnostics,0,0);
            recover.Text="恢复新手起点";recover.Dock=DockStyle.Fill;recover.BackColor=Theme.Surface;recover.ForeColor=Theme.Muted;recover.Font=new Font(Font.FontFamily,9.5f);recover.AccessibleName="恢复新手起点";((SoftButton)recover).Quiet=true;recover.Click+=async delegate{activeOperation=recover;await RecoverTutorial();};help.Controls.Add(recover,2,0);
            GlassPanel.TransparentChildren(launcherSettings);Resize+=delegate{PlaceLauncherPanels();};PlaceLauncherPanels();
        }
        Control PanelHeading(string title,Action close){var row=Grid(2,1);row.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));row.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,36));row.RowStyles.Add(new RowStyle(SizeType.Percent,100));row.Controls.Add(new Label {Text=title,Dock=DockStyle.Fill,TextAlign=ContentAlignment.MiddleLeft,ForeColor=Theme.Ink,Font=new Font(Font.FontFamily,17,FontStyle.Bold),Margin=Padding.Empty},0,0);var button=IconButton("关闭"+title,"close",close);button.BackColor=Theme.Surface;row.Controls.Add(button,1,0);return row;}
        void BuildAccountPanel(){
            accountPanel=new GlassPanel(heroScene) {Visible=false,Size=new Size(448,414),Padding=new Padding(26,22,26,22),AccessibleName="朋友服登录"};Controls.Add(accountPanel);
            var form=Grid(1,11);foreach(int h in new[]{44,30,18,22,52,12,22,52,40,58})form.RowStyles.Add(new RowStyle(SizeType.Absolute,h));form.RowStyles.Add(new RowStyle(SizeType.Percent,100));accountPanel.Controls.Add(form);
            form.Controls.Add(PanelHeading("登录朋友服",()=>SetAccountOpen(false)),0,0);form.Controls.Add(Caption("账号与存档按本地、联网模式分别保存。",9.5f),0,1);
            form.Controls.Add(Caption("账号",10.5f),0,3);nameBox.MaxLength=24;nameBox.AccessibleName="账号";form.Controls.Add(new MotionInput(nameBox,"user"){Dock=DockStyle.Fill,Padding=new Padding(38,14,12,10),Placeholder="输入账号",TabIndex=0},0,4);
            form.Controls.Add(Caption("密码",10.5f),0,6);passwordBox.UseSystemPasswordChar=true;passwordBox.MaxLength=64;passwordBox.AccessibleName="密码";var password=new MotionInput(passwordBox,"lock"){Dock=DockStyle.Fill,Padding=new Padding(38,14,40,10),Placeholder="输入密码",TabIndex=1};form.Controls.Add(password,0,7);nameBox.Font=passwordBox.Font=new Font(Font.FontFamily,12);
            var eye=IconButton("显示或隐藏密码","eye",()=>{passwordBox.UseSystemPasswordChar=!passwordBox.UseSystemPasswordChar;});eye.Size=new Size(32,32);eye.Dock=DockStyle.None;eye.Anchor=AnchorStyles.Top|AnchorStyles.Right;eye.BackColor=Theme.Field;password.Controls.Add(eye);eye.BringToFront();password.Layout+=delegate{eye.Location=new Point(password.Width-37,10);};
            var options=Grid(2,1);options.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,65));options.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,35));options.RowStyles.Add(new RowStyle(SizeType.Percent,100));form.Controls.Add(options,0,8);
            remember.Text="记住登录和密码";remember.Checked=true;remember.Dock=DockStyle.Fill;remember.ForeColor=Theme.Muted;remember.Font=new Font(Font.FontFamily,9.5f);remember.AccessibleName="记住登录和密码，本机加密保存";remember.Margin=Padding.Empty;options.Controls.Add(remember,0,0);
            register.Text="创建账号";register.Dock=DockStyle.Fill;register.BackColor=Theme.Surface;register.ForeColor=Theme.Cyan;register.Font=new Font(Font.FontFamily,10);register.AccessibleName="创建账号";((SoftButton)register).Quiet=true;register.Click+=delegate(object sender,EventArgs e){Register(sender,e);};options.Controls.Add(register,1,0);
            accountContinue=new SoftButton {Text="登录并进入游戏",Glyph="play",Gradient=true,Dock=DockStyle.Fill,BackColor=Theme.Primary,ForeColor=Color.White,Font=new Font(Font.FontFamily,14,FontStyle.Bold),AccessibleName="登录并开始游戏"};accountContinue.Click+=async delegate{SetAccountOpen(false);activeOperation=login;await LoginAndStart();};form.Controls.Add(accountContinue,0,9);GlassPanel.TransparentChildren(accountPanel);PlaceLauncherPanels();
        }
        void PlaceLauncherPanels(){if(launcherSettings!=null)launcherSettings.Location=new Point(ClientSize.Width-launcherSettings.Width-32,58);if(accountPanel!=null)accountPanel.Location=new Point(62,Math.Max(58,heroScene.Top+(heroScene.Height-accountPanel.Height)/2));}
        public object VerifyGlassForDesignTest(){return new {header=headerGlass.VerifyMaterialForTest(),account=((GlassPanel)accountPanel).VerifyMaterialForTest(),settings=((GlassPanel)launcherSettings).VerifyMaterialForTest(),information=information.VerifyFlatForTest()};}
        void SetSettingsOpen(bool show){launcherSettings.Visible=show;if(show){if(accountPanel!=null)accountPanel.Visible=false;AcceptButton=login;launcherSettings.BringToFront();browse.Focus();}else settingsToggle.Focus();}
        void ToggleLauncherSettings(){SetSettingsOpen(!launcherSettings.Visible);}
        void SetAccountOpen(bool show){accountPanel.Visible=show;if(show){launcherSettings.Visible=false;accountPanel.BringToFront();AcceptButton=accountContinue;if(nameBox.TextLength==0)nameBox.Focus();else passwordBox.Focus();}else{AcceptButton=login;accountSummary.Focus();}}
        public void SettingsForDesignTest(bool visible){SetSettingsOpen(visible);}
        public void AccountForDesignTest(bool visible){SetAccountOpen(visible);}
        public void VerifyLauncherUxForTest(){
            Show();Application.DoEvents();settingsToggle.PerformClick();if(!launcherSettings.Visible)throw new Exception("Settings did not open");OnKeyDown(new KeyEventArgs(Keys.Escape));if(launcherSettings.Visible)throw new Exception("Escape did not close settings");
            accountSummary.PerformClick();if(!accountPanel.Visible||AcceptButton!=accountContinue)throw new Exception("Account entry did not open");OnKeyDown(new KeyEventArgs(Keys.Escape));if(accountPanel.Visible||AcceptButton!=login)throw new Exception("Account return failed");
            SetBusy(true);if(login.Enabled||accountContinue.Enabled||browse.Enabled||sourcePull.Enabled||localChoice.Enabled||onlineChoice.Enabled)throw new Exception("Busy controls remained enabled");SetBusy(false);
            if(!pathBox.ReadOnly||pathBox.TabStop||nameBox.Font.Size<11||passwordBox.Font.Size<11)throw new Exception("Login readability or directory behavior regressed");
            if(LaunchMode.Local)throw new Exception("UI validation fixture must use online mode");
            string previous=clientPath;string fixture=Path.Combine(Program.DataRoot,"ui-client-"+Guid.NewGuid().ToString("N"));
            try {
                clientPath="";login.PerformClick();if(!launcherSettings.Visible)throw new Exception("Missing client did not open directory settings");SetSettingsOpen(false);
                Directory.CreateDirectory(fixture);clientPath=Path.Combine(fixture,"x2_dx11.exe");File.WriteAllBytes(clientPath,new byte[0]);nameBox.Clear();passwordBox.Clear();
                login.PerformClick();if(!accountPanel.Visible||AcceptButton!=accountContinue)throw new Exception("Missing credentials did not open login");SetAccountOpen(false);
            }finally{clientPath=previous;if(File.Exists(Path.Combine(fixture,"x2_dx11.exe")))File.Delete(Path.Combine(fixture,"x2_dx11.exe"));if(Directory.Exists(fixture))Directory.Delete(fixture);}
            Status("选择客户端并登录后，即可开始游戏。");Hide();
        }
    }
}
