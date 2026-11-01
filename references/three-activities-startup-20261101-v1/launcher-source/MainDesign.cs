using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Reflection;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace ElsFriends {
    class Wordmark:Control {
        public Wordmark(){DoubleBuffered=true;}
        protected override void OnPaint(PaintEventArgs e){
            var g=e.Graphics;g.SmoothingMode=SmoothingMode.AntiAlias;
            var top=new PointF(21,10);var left=new PointF(7,27);var right=new PointF(35,27);var bottom=new PointF(21,45);var middle=new PointF(21,28);
            using(var b=new SolidBrush(Color.FromArgb(91,216,237)))g.FillPolygon(b,new[]{top,left,middle});
            using(var b=new SolidBrush(Theme.Cyan))g.FillPolygon(b,new[]{top,right,middle});
            using(var b=new SolidBrush(Color.FromArgb(15,120,163)))g.FillPolygon(b,new[]{left,bottom,middle});
            using(var b=new SolidBrush(Color.FromArgb(31,179,207)))g.FillPolygon(b,new[]{right,bottom,middle});
            using(var f=new Font("Microsoft YaHei UI",16,FontStyle.Bold))TextRenderer.DrawText(g,"艾尔之光",f,new Rectangle(49,5,145,30),Theme.Ink,TextFormatFlags.NoPadding);
            using(var f=new Font("Segoe UI",6.8f,FontStyle.Bold))TextRenderer.DrawText(g,"E L R I O S   ·   U N I F I E D",f,new Rectangle(51,35,200,16),Theme.Muted,TextFormatFlags.NoPadding);
        }
    }
    class AdventureScene:Panel {
        readonly Image image;
        public AdventureScene(){DoubleBuffered=true;using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("ElsFriends.Ruben"))using(var original=Image.FromStream(stream))image=new Bitmap(original);}
        protected override void Dispose(bool disposing){if(disposing)image.Dispose();base.Dispose(disposing);}
        protected override void OnPaintBackground(PaintEventArgs e){
            var g=e.Graphics;g.Clear(Theme.Canvas);g.SmoothingMode=SmoothingMode.AntiAlias;g.TextRenderingHint=System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
            using(var path=Theme.Round(new RectangleF(0,0,Width-1,Height-1),23)){
                var save=g.Save();g.SetClip(path);float scale=Math.Max(Width/(float)image.Width,Height/(float)image.Height);float w=image.Width*scale,h=image.Height*scale;
                g.InterpolationMode=InterpolationMode.HighQualityBicubic;g.DrawImage(image,new RectangleF((Width-w)*.50f,(Height-h)*.50f,w,h));
                using(var shade=new LinearGradientBrush(ClientRectangle,Color.FromArgb(25,11,35,48),Color.FromArgb(224,11,35,48),90f))g.FillRectangle(shade,ClientRectangle);
                using(var pill=Theme.Round(new RectangleF(24,24,144,29),14))using(var b=new SolidBrush(Color.FromArgb(210,Color.White)))g.FillPath(b,pill);
                using(var f=new Font("Microsoft YaHei UI",8,FontStyle.Bold))TextRenderer.DrawText(g,"魔奇  /  RUBEN",f,new Rectangle(39,30,124,19),Color.FromArgb(31,89,104),TextFormatFlags.NoPadding);
                using(var f=new Font("Segoe UI",7.8f,FontStyle.Bold))TextRenderer.DrawText(g,"A D V E N T U R E   A W A I T S",f,new Rectangle(32,Height-192,Width-64,24),Color.FromArgb(167,229,234),TextFormatFlags.NoPadding);
                using(var f=new Font("Microsoft YaHei UI",29,FontStyle.Bold))g.DrawString("你的世界，\n随时出发。",f,Brushes.White,new RectangleF(27,Height-163,Width-50,106));
                using(var f=new Font("Microsoft YaHei UI",9))g.DrawString("独自探索，或与朋友再次相遇。",f,Brushes.White,32,Height-42);
                g.Restore(save);
            }
        }
    }
    partial class MainForm {
        Button activeOperation;
        void BuildDesign(){
            var shell=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=1,RowCount=3,Margin=Padding.Empty,Padding=Padding.Empty};
            shell.RowStyles.Add(new RowStyle(SizeType.Absolute,74));shell.RowStyles.Add(new RowStyle(SizeType.Percent,100));shell.RowStyles.Add(new RowStyle(SizeType.Absolute,30));Controls.Add(shell);
            var top=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=4,RowCount=1,Padding=new Padding(23,9,12,9),Margin=Padding.Empty,BackColor=Theme.Canvas};
            top.RowStyles.Add(new RowStyle(SizeType.Percent,100));
            top.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,275));top.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));top.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,182));top.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,111));
            var wordmark=new Wordmark {Dock=DockStyle.Fill,Margin=Padding.Empty};top.Controls.Add(wordmark,0,0);
            server.Text="正在连接朋友服…";server.Font=new Font(Font.FontFamily,8);server.ForeColor=Color.FromArgb(63,157,134);server.Dock=DockStyle.Fill;server.TextAlign=ContentAlignment.MiddleRight;server.Padding=new Padding(0,0,19,0);top.Controls.Add(server,1,0);
            update.Text="V"+AutoUpdate.Version+" · 检查更新";update.Dock=DockStyle.Fill;update.BackColor=Theme.Canvas;update.ForeColor=Theme.Cyan;update.Font=new Font(Font.FontFamily,8);update.Margin=new Padding(0,9,12,9);update.AccessibleName="检查启动器更新";((SoftButton)update).Glyph="refresh";((SoftButton)update).Compact=true;
            update.Click+=async delegate{if(readyUpdate!=null){if(busy){Status("请正常退出游戏后，再更新启动器。");return;}AutoUpdate.PendingLauncher=readyUpdate;Close();}else await CheckUpdate(true);};top.Controls.Add(update,2,0);
            var controls=WindowControls(true);controls.Margin=new Padding(0,11,0,0);top.Controls.Add(controls,3,0);shell.Controls.Add(top,0,0);
            BindWindowDrag(top);BindWindowDrag(wordmark);BindWindowDrag(server);
            var content=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=3,RowCount=1,Padding=new Padding(24,4,24,10),Margin=Padding.Empty};
            content.RowStyles.Add(new RowStyle(SizeType.Percent,100));
            content.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,55));content.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,22));content.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,45));shell.Controls.Add(content,0,1);
            var left=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=1,RowCount=5,Margin=Padding.Empty};left.RowStyles.Add(new RowStyle(SizeType.Percent,100));left.RowStyles.Add(new RowStyle(SizeType.Absolute,14));left.RowStyles.Add(new RowStyle(SizeType.Absolute,174));left.RowStyles.Add(new RowStyle(SizeType.Absolute,14));left.RowStyles.Add(new RowStyle(SizeType.Absolute,90));content.Controls.Add(left,0,0);
            left.Controls.Add(new AdventureScene {Dock=DockStyle.Fill,Margin=Padding.Empty},0,0);
            var resources=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=3,RowCount=1,Margin=Padding.Empty};resources.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));resources.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,14));resources.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));left.Controls.Add(resources,0,4);
            BuildSourceCard(left);
            resources.RowStyles.Add(new RowStyle(SizeType.Percent,100));
            var clientDownload=new ToolCard {Text="客户端下载",Subtitle="完整客户端 · 提取码 jrg6",Glyph="download",Dock=DockStyle.Fill,BackColor=Color.White,ForeColor=Theme.Cyan,AccessibleName="客户端下载，提取码 jrg6"};clientDownload.Click+=delegate{OpenExternal(AutoUpdate.ClientUrl);};resources.Controls.Add(clientDownload,0,0);
            var progressPage=new ToolCard {Text="项目进度",Subtitle="查看修复进度与待办",Glyph="progress",Dock=DockStyle.Fill,BackColor=Color.White,ForeColor=Theme.Cyan,AccessibleName="打开线上项目进度表"};progressPage.Click+=delegate{OpenExternal(AutoUpdate.ProgressUrl);};resources.Controls.Add(progressPage,2,0);
            var card=new SoftPanel {Dock=DockStyle.Fill,Padding=new Padding(25,20,25,16),Margin=Padding.Empty};content.Controls.Add(card,2,0);
            var form=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=1,RowCount=18,Margin=Padding.Empty};card.Controls.Add(form);
            int[] heights={15,39,25,46,20,42,8,20,42,8,20,42,31,50,33,66,0,32};for(int i=0;i<heights.Length;i++)form.RowStyles.Add(i==16?new RowStyle(SizeType.Percent,100):new RowStyle(SizeType.Absolute,heights[i]));
            form.Controls.Add(new Label {Text="Y O U R   N E X T   C H A P T E R",Dock=DockStyle.Fill,Font=new Font("Segoe UI",7,FontStyle.Bold),ForeColor=Theme.Cyan,Margin=Padding.Empty},0,0);
            form.Controls.Add(new Label {Text="下一站，艾里奥斯",Dock=DockStyle.Fill,Font=new Font(Font.FontFamily,24,FontStyle.Bold),ForeColor=Theme.Ink,Margin=Padding.Empty},0,1);
            modeSubtitle.Dock=DockStyle.Fill;modeSubtitle.ForeColor=Theme.Muted;modeSubtitle.Margin=Padding.Empty;form.Controls.Add(modeSubtitle,0,2);BuildModeSelector(form);
            AddLabel(form,"客户端目录",4);
            var fileRow=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=2,Margin=Padding.Empty};fileRow.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));fileRow.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,76));form.Controls.Add(fileRow,0,5);
            fileRow.RowStyles.Add(new RowStyle(SizeType.Percent,100));
            pathBox.ReadOnly=true;pathBox.AccessibleName="客户端目录";var pathFrame=new MotionInput(pathBox,"folder"){Dock=DockStyle.Fill,Margin=new Padding(0,0,8,0)};pathBox.Font=new Font(Font.FontFamily,8);fileRow.Controls.Add(pathFrame,0,0);
            browse.Text="选择";browse.Dock=DockStyle.Fill;browse.BackColor=Color.FromArgb(237,247,251);browse.ForeColor=Theme.Cyan;browse.AccessibleName="选择客户端目录";browse.Click+=ChooseClient;fileRow.Controls.Add(browse,1,0);
            AddLabel(form,"账号",7);nameBox.MaxLength=24;nameBox.AccessibleName="账号";form.Controls.Add(new MotionInput(nameBox,"user"){Dock=DockStyle.Fill},0,8);
            AddLabel(form,"密码",10);passwordBox.UseSystemPasswordChar=true;passwordBox.MaxLength=64;passwordBox.AccessibleName="密码";
            var passwordFrame=new MotionInput(passwordBox,"lock"){Dock=DockStyle.Fill,Padding=new Padding(38,11,42,8)};form.Controls.Add(passwordFrame,0,11);
            var showPassword=new SoftButton {Text="",Glyph="eye",Compact=true,Size=new Size(28,28),BackColor=Color.White,ForeColor=Theme.Muted,Anchor=AnchorStyles.Top|AnchorStyles.Right,AccessibleName="显示或隐藏密码",TabIndex=1};passwordFrame.Controls.Add(showPassword);showPassword.BringToFront();passwordFrame.Layout+=delegate{showPassword.Location=new Point(passwordFrame.Width-34,7);};showPassword.Location=new Point(passwordFrame.Width-34,7);showPassword.Click+=delegate{passwordBox.UseSystemPasswordChar=!passwordBox.UseSystemPasswordChar;showPassword.ForeColor=passwordBox.UseSystemPasswordChar?Theme.Muted:Theme.Cyan;};
            remember.Text="记住登录和密码";remember.Checked=true;remember.Dock=DockStyle.Fill;remember.ForeColor=Theme.Muted;remember.Font=new Font(Font.FontFamily,8.5f);remember.Margin=new Padding(1,0,0,0);remember.AccessibleName="记住登录和密码，本机加密保存";form.Controls.Add(remember,0,12);
            login.Text="登录并开始冒险";login.Dock=DockStyle.Fill;login.BackColor=Theme.Coral;login.ForeColor=Color.White;login.Font=new Font(Font.FontFamily,11,FontStyle.Bold);login.AccessibleName="登录并启动游戏";((SoftButton)login).Glyph="arrow";login.Click+=async delegate{activeOperation=login;await LoginAndStart();};form.Controls.Add(login,0,13);
            register.Text="第一次来？创建账号";register.Dock=DockStyle.Fill;register.BackColor=Color.White;register.ForeColor=Theme.Cyan;register.Font=new Font(Font.FontFamily,8.5f);register.Margin=new Padding(0,4,0,0);register.AccessibleName="注册朋友服账号";register.Click+=delegate(object sender,EventArgs e){if(LaunchMode.Local)OpenManager("gm");else Register(sender,e);};form.Controls.Add(register,0,14);
            var statusPanel=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=1,RowCount=2,Margin=Padding.Empty};statusPanel.RowStyles.Add(new RowStyle(SizeType.Percent,100));statusPanel.RowStyles.Add(new RowStyle(SizeType.Absolute,7));form.Controls.Add(statusPanel,0,15);journeyProgress.Dock=DockStyle.Fill;journeyProgress.Margin=Padding.Empty;statusPanel.Controls.Add(journeyProgress,0,1);
            feedback.Text="请选择完整客户端目录，然后登录。";feedback.Dock=DockStyle.Fill;feedback.ForeColor=Theme.Muted;feedback.Font=new Font(Font.FontFamily,8);feedback.Padding=new Padding(0,8,0,0);feedback.Margin=Padding.Empty;statusPanel.Controls.Add(feedback,0,0);
            var help=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=3,RowCount=1,Margin=Padding.Empty};help.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));help.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,10));help.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,50));form.Controls.Add(help,0,17);
            help.RowStyles.Add(new RowStyle(SizeType.Percent,100));
            diagnostics.Text="诊断与反馈";diagnostics.Dock=DockStyle.Fill;diagnostics.BackColor=Color.White;diagnostics.ForeColor=Theme.Muted;diagnostics.Font=new Font(Font.FontFamily,8);diagnostics.AccessibleName="生成或上传诊断报告";((SoftButton)diagnostics).Compact=true;((SoftButton)diagnostics).Glyph="help";diagnostics.Click+=async delegate{await OpenDiagnostics();};help.Controls.Add(diagnostics,0,0);
            recover.Text="恢复新手起点";recover.Dock=DockStyle.Fill;recover.BackColor=Color.White;recover.ForeColor=Theme.Muted;recover.Font=new Font(Font.FontFamily,8);recover.AccessibleName="恢复新手起点";((SoftButton)recover).Compact=true;recover.Click+=async delegate{if(LaunchMode.Local){OpenManager("backups");return;}activeOperation=recover;await RecoverTutorial();};help.Controls.Add(recover,2,0);
            var footer=new Label {Text="ELRIOS  /  JOURNEY TOGETHER                                        本地与线上 · 自由选择你的冒险",Dock=DockStyle.Fill,Padding=new Padding(26,3,0,0),ForeColor=Theme.Muted,Font=new Font(Font.FontFamily,7.5f),Margin=Padding.Empty};shell.Controls.Add(footer,0,2);
        }
    }
}
