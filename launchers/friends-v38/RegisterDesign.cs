using System;
using System.Drawing;
using System.Windows.Forms;

namespace ElsFriends {
    partial class RegisterForm {
        Button BuildRegistration(string name){
            Text="注册朋友服账号";ClientSize=new Size(480,510);MinimumSize=Size;FormBorderStyle=FormBorderStyle.None;MaximizeBox=MinimizeBox=false;ShowInTaskbar=false;StartPosition=FormStartPosition.CenterParent;Font=new Font("Microsoft YaHei UI",9);ForeColor=Theme.Ink;BackColor=Theme.Canvas;
            var outer=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=1,RowCount=2,Margin=Padding.Empty};outer.RowStyles.Add(new RowStyle(SizeType.Absolute,52));outer.RowStyles.Add(new RowStyle(SizeType.Percent,100));Controls.Add(outer);
            var header=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=2,RowCount=1,Margin=Padding.Empty,Padding=new Padding(23,9,11,9)};header.RowStyles.Add(new RowStyle(SizeType.Percent,100));header.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));header.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,35));
            var heading=new Label {Text="E L R I O S    /    注册账号",Dock=DockStyle.Fill,TextAlign=ContentAlignment.MiddleLeft,ForeColor=Theme.Muted,Font=new Font(Font.FontFamily,8),Margin=Padding.Empty};header.Controls.Add(heading,0,0);header.Controls.Add(WindowControls(false),1,0);outer.Controls.Add(header,0,0);BindWindowDrag(header);BindWindowDrag(heading);
            var wrapper=new Panel {Dock=DockStyle.Fill,Padding=new Padding(20,6,20,20),Margin=Padding.Empty};outer.Controls.Add(wrapper,0,1);var card=new SoftPanel {Dock=DockStyle.Fill,Padding=new Padding(25,22,25,19)};wrapper.Controls.Add(card);
            var form=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=1,RowCount=14,Margin=Padding.Empty};card.Controls.Add(form);foreach(int height in new[]{36,29,21,42,11,21,42,11,21,42,11,43,42})form.RowStyles.Add(new RowStyle(SizeType.Absolute,height));form.RowStyles.Add(new RowStyle(SizeType.Percent,100));
            form.Controls.Add(new Label {Text="开启你的冒险",Dock=DockStyle.Fill,Margin=Padding.Empty,Font=new Font(Font.FontFamily,22,FontStyle.Bold)},0,0);
            form.Controls.Add(new Label {Text="创建账号，一起出发。",Dock=DockStyle.Fill,Margin=Padding.Empty,ForeColor=Theme.Muted},0,1);
            var inputs=new[]{account,password,confirm};var labels=new[]{"账号","密码","确认密码"};var rows=new[]{2,5,8};
            for(int i=0;i<inputs.Length;i++){form.Controls.Add(new Label {Text=labels[i],Dock=DockStyle.Fill,Margin=Padding.Empty},0,rows[i]);inputs[i].AccessibleName=labels[i];inputs[i].MaxLength=i==0?24:64;form.Controls.Add(new MotionInput(inputs[i],i==0?"user":"lock"){Dock=DockStyle.Fill},0,rows[i]+1);}
            account.Text=name;password.UseSystemPasswordChar=confirm.UseSystemPasswordChar=true;
            form.Controls.Add(new Label {Text="账号 3–24 位，小写字母开头，可含数字和下划线。\n密码 8–64 个字符。",Dock=DockStyle.Fill,Margin=Padding.Empty,Padding=new Padding(0,3,0,0),Font=new Font(Font.FontFamily,8),ForeColor=Theme.Muted},0,11);
            var actions=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=2,RowCount=1,Margin=Padding.Empty};actions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));actions.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,200));actions.RowStyles.Add(new RowStyle(SizeType.Percent,100));form.Controls.Add(actions,0,12);
            var submit=new SoftButton {Text="创建账号并登录",Glyph="arrow",Dock=DockStyle.Fill,BackColor=Theme.Coral,ForeColor=Color.White,Font=new Font(Font.FontFamily,9,FontStyle.Bold),AccessibleName="创建账号并登录"};actions.Controls.Add(submit,1,0);AcceptButton=submit;return submit;
        }
    }
}
