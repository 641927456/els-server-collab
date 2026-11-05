using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace ElsFriends {
    class DiscordButton:SoftButton {
        static readonly Color Blurple=Color.FromArgb(88,101,242);
        public DiscordButton(){
            Text="加入 DC 交流频道";
            AccessibleName="加入 Discord 交流频道，在浏览器中打开邀请";
            BackColor=Color.FromArgb(240,240,255);ForeColor=Blurple;
        }
        protected override void PaintContent(Graphics g,Rectangle area,Color ink,float hover){
            float x=area.Left+14,y=area.Top+(area.Height-40)/2f-hover;
            using(var tile=Theme.Round(new RectangleF(x,y,40,40),12))
            using(var fill=new LinearGradientBrush(new RectangleF(x,y,40,40),Blurple,Color.FromArgb(117,86,221),45f))g.FillPath(fill,tile);
            var state=g.Save();g.TranslateTransform(x+7,y+9);g.ScaleTransform(26f/24,22f/20);
            using(var face=new GraphicsPath()){
                face.AddBezier(5,4,7,2,17,2,19,4);
                face.AddBezier(19,4,21,7,23,12,22,15);
                face.AddBezier(22,15,20,17,18,18,16,18);
                face.AddLine(16,18,15,16);
                face.AddBezier(15,16,13,17,11,17,9,16);
                face.AddLine(9,16,8,18);
                face.AddBezier(8,18,6,18,4,17,2,15);
                face.AddBezier(2,15,1,12,3,7,5,4);
                face.CloseFigure();g.FillPath(Brushes.White,face);
            }
            using(var eye=new SolidBrush(Blurple)){g.FillEllipse(eye,7,9,3,4);g.FillEllipse(eye,14,9,3,4);}
            g.Restore(state);
            using(var title=new Font("Segoe UI",7,FontStyle.Bold))
                TextRenderer.DrawText(g,"D I S C O R D",title,new Rectangle(area.Left+67,area.Top+10,area.Width-100,15),ink,TextFormatFlags.NoPadding|TextFormatFlags.SingleLine);
            using(var label=new Font("Microsoft YaHei UI",10,FontStyle.Bold))
                TextRenderer.DrawText(g,Text,label,new Rectangle(area.Left+66,area.Top+28,area.Width-91,24),Enabled?Theme.Ink:ink,TextFormatFlags.NoPadding|TextFormatFlags.SingleLine);
            Glyphs.Draw(g,"external",new RectangleF(area.Right-25+hover*2,area.Top+(area.Height-16)/2f,16,16),ink,1.5f);
        }
    }
    partial class MainForm {
        internal const string DiscordInviteUrl="https://discord.gg/HPNGMA247";
        internal const string ProjectNotice="本项目仅供学习交流使用，任何获取到的资源请24小时内删除，本项目不参与盈利相关事宜。";
        Control BuildCommunityFooter(){
            var footer=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=3,RowCount=1,Padding=new Padding(24,7,24,15),Margin=Padding.Empty};
            footer.RowStyles.Add(new RowStyle(SizeType.Percent,100));
            footer.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,270));
            footer.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,24));
            footer.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
            var discord=new DiscordButton {Dock=DockStyle.Fill,Margin=Padding.Empty,Name="discord-community"};
            discord.Click+=delegate{OpenExternal(DiscordInviteUrl);};footer.Controls.Add(discord,0,0);
            footer.Controls.Add(new Label {Name="project-notice",Text=ProjectNotice,AccessibleName=ProjectNotice,Dock=DockStyle.Fill,TextAlign=ContentAlignment.MiddleLeft,ForeColor=Theme.Muted,Font=new Font(Font.FontFamily,8.5f),Margin=Padding.Empty},2,0);
            return footer;
        }
    }
}
