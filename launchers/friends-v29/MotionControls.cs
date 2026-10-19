using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

namespace ElsFriends {
    interface IMotion {bool Step(float seconds);bool Alive {get;}}
    static class MotionClock {
        static readonly HashSet<IMotion> active=new HashSet<IMotion>();
        static readonly Timer timer=new Timer {Interval=16};
        static readonly System.Diagnostics.Stopwatch clock=System.Diagnostics.Stopwatch.StartNew();
        static long last;
        public static bool Reduced {get{return Environment.GetEnvironmentVariable("ELS_REDUCE_MOTION")=="1";}}
        static MotionClock(){timer.Tick+=delegate{long now=clock.ElapsedMilliseconds;float dt=Math.Min(.05f,Math.Max(.001f,(now-last)/1000f));last=now;foreach(var item in new List<IMotion>(active))if(!item.Alive||!item.Step(dt))active.Remove(item);if(active.Count==0)timer.Stop();};}
        public static void Wake(IMotion item){if(!item.Alive)return;active.Add(item);if(!timer.Enabled){last=clock.ElapsedMilliseconds;timer.Start();}}
        public static void Forget(IMotion item){active.Remove(item);if(active.Count==0)timer.Stop();}
        public static int ActiveCount {get{return active.Count;}}
        public static float Approach(float from,float to,float dt){if(Reduced||Math.Abs(from-to)<.003f)return to;return from+(to-from)*(1-(float)Math.Exp(-dt*18));}
        public static Color Mix(Color a,Color b,float t){t=Math.Max(0,Math.Min(1,t));return Color.FromArgb((int)(a.A+(b.A-a.A)*t),(int)(a.R+(b.R-a.R)*t),(int)(a.G+(b.G-a.G)*t),(int)(a.B+(b.B-a.B)*t));}
        public static Color ParentColor(Control control){for(var p=control.Parent;p!=null;p=p.Parent)if(p.BackColor.A==255)return p.BackColor;return Theme.Canvas;}
    }
    class SoftButton:Button,IMotion {
        bool over,down,activity;float hover,press,disabled,ripple=1,angle,flash;
        int progress=-1;PointF origin;Color flashColor=Theme.Cyan;
        public string Glyph="";
        public bool Compact;
        public bool Activity {get{return activity;}set{if(activity==value)return;activity=value;if(value)MotionClock.Wake(this);Invalidate();}}
        public int ProgressValue {get{return progress;}set{progress=value;Invalidate();}}
        public bool Alive {get{return !IsDisposed&&IsHandleCreated;}}
        public float HoverAmount {get{return hover;}}
        public float PressAmount {get{return press;}}
        public SoftButton(){DoubleBuffered=true;SetStyle(ControlStyles.AllPaintingInWmPaint|ControlStyles.UserPaint|ControlStyles.OptimizedDoubleBuffer,true);FlatStyle=FlatStyle.Flat;FlatAppearance.BorderSize=0;Cursor=Cursors.Hand;BackColor=Color.White;ForeColor=Theme.Cyan;UseVisualStyleBackColor=false;Margin=Padding.Empty;}
        protected override void Dispose(bool disposing){if(disposing)MotionClock.Forget(this);base.Dispose(disposing);}
        protected override void OnMouseEnter(EventArgs e){over=true;MotionClock.Wake(this);base.OnMouseEnter(e);}
        protected override void OnMouseLeave(EventArgs e){over=false;down=false;MotionClock.Wake(this);base.OnMouseLeave(e);}
        protected override void OnMouseDown(MouseEventArgs e){if(e.Button==MouseButtons.Left&&Enabled&&!activity){down=true;origin=e.Location;MotionClock.Wake(this);}base.OnMouseDown(e);}
        protected override void OnMouseUp(MouseEventArgs e){down=false;MotionClock.Wake(this);base.OnMouseUp(e);}
        protected override void OnKeyDown(KeyEventArgs e){if((e.KeyCode==Keys.Space||e.KeyCode==Keys.Enter)&&Enabled&&!activity){down=true;origin=new PointF(Width/2f,Height/2f);MotionClock.Wake(this);}base.OnKeyDown(e);}
        protected override void OnKeyUp(KeyEventArgs e){down=false;MotionClock.Wake(this);base.OnKeyUp(e);}
        protected override void OnGotFocus(EventArgs e){MotionClock.Wake(this);Invalidate();base.OnGotFocus(e);}
        protected override void OnLostFocus(EventArgs e){down=false;MotionClock.Wake(this);Invalidate();base.OnLostFocus(e);}
        protected override void OnEnabledChanged(EventArgs e){down=false;if(!IsHandleCreated)disabled=Enabled?0:1;else MotionClock.Wake(this);base.OnEnabledChanged(e);}
        protected override void OnClick(EventArgs e){if(!Enabled||activity)return;ripple=0;if(origin==PointF.Empty)origin=new PointF(Width/2f,Height/2f);MotionClock.Wake(this);base.OnClick(e);}
        public void Feedback(bool success){flash=1;flashColor=success?Color.FromArgb(39,166,126):Color.FromArgb(222,83,103);MotionClock.Wake(this);Invalidate();}
        public bool Step(float dt){hover=MotionClock.Approach(hover,over&&Enabled?1:0,dt);press=MotionClock.Approach(press,down&&Enabled?1:0,dt);disabled=MotionClock.Approach(disabled,Enabled?0:1,dt);ripple=Math.Min(1,ripple+dt*2.6f);flash=Math.Max(0,flash-dt*1.5f);if(activity)angle=(angle+dt*230)%360;Invalidate();return activity||Math.Abs(hover-(over&&Enabled?1:0))>.003f||Math.Abs(press-(down&&Enabled?1:0))>.003f||Math.Abs(disabled-(Enabled?0:1))>.003f||ripple<1||flash>0;}
        protected override void OnPaint(PaintEventArgs e){
            var g=e.Graphics;g.Clear(MotionClock.ParentColor(this));g.SmoothingMode=SmoothingMode.AntiAlias;
            float inset=press*(Compact?1:1.5f);var rect=new RectangleF(1+inset,1+inset,Math.Max(1,Width-3-inset*2),Math.Max(1,Height-3-inset*2));
            bool primary=BackColor==Theme.Coral;Color normal=BackColor.A==0?Color.White:BackColor;
            Color target=primary?Color.FromArgb(242,76,107):MotionClock.Mix(normal,Color.FromArgb(226,242,249),.65f);
            Color fill=MotionClock.Mix(normal,target,hover);fill=MotionClock.Mix(fill,primary?Color.FromArgb(217,58,93):Color.FromArgb(219,235,244),press*.6f);fill=MotionClock.Mix(fill,Color.FromArgb(234,238,244),disabled*.85f);
            Color ink=MotionClock.Mix(ForeColor,Color.FromArgb(157,169,185),disabled);
            using(var path=Theme.Round(rect,Compact?9:13)) {
                using(var brush=new SolidBrush(fill))g.FillPath(brush,path);
                Color border=Focused&&Enabled?Theme.Cyan:MotionClock.Mix(Color.FromArgb(229,235,243),Color.FromArgb(155,207,225),hover);
                if(flash>0)border=MotionClock.Mix(border,flashColor,flash);
                if(!primary||Focused||flash>0)using(var pen=new Pen(border,Focused&&Enabled?1.8f:1))g.DrawPath(pen,path);
                if(ripple<1&&!MotionClock.Reduced){var state=g.Save();g.SetClip(path);float radius=(float)Math.Sqrt(Width*Width+Height*Height)*ripple;using(var brush=new SolidBrush(Color.FromArgb((int)(35*(1-ripple)),primary?Color.White:Theme.Cyan)))g.FillEllipse(brush,origin.X-radius,origin.Y-radius,radius*2,radius*2);g.Restore(state);}
                if(primary&&hover>0&&!MotionClock.Reduced){var state=g.Save();g.SetClip(path);using(var brush=new LinearGradientBrush(rect,Color.FromArgb((int)(18*hover),Color.White),Color.Transparent,90f))g.FillRectangle(brush,rect);g.Restore(state);}
            }
            var content=Rectangle.Round(rect);content.Offset(0,(int)Math.Round(press));
            PaintContent(g,content,ink,hover);
            if(activity){using(var pen=new Pen(ink,1.8f)){pen.StartCap=pen.EndCap=LineCap.Round;g.DrawArc(pen,new RectangleF(rect.X+13,rect.Y+(rect.Height-13)/2,13,13),angle,245);}}
            if(progress>=0){float width=Math.Max(0,Math.Min(100,progress))/100f*(rect.Width-18);using(var pen=new Pen(primary?Color.White:Theme.Cyan,2)){pen.StartCap=pen.EndCap=LineCap.Round;if(width>0)g.DrawLine(pen,rect.X+9,rect.Bottom-5,rect.X+9+width,rect.Bottom-5);}}
        }
        protected virtual void PaintContent(Graphics g,Rectangle area,Color ink,float hoverAmount){
            if(Glyph.Length>0&&Text.Length==0&&!activity){Glyphs.Draw(g,Glyph,new RectangleF(area.Left+(area.Width-17)/2f,area.Top+(area.Height-17)/2f,17,17),ink,1.6f);return;}
            if(Glyph.Length>0&&!activity){float x=area.Left+15;Glyphs.Draw(g,Glyph,new RectangleF(x,area.Top+(area.Height-17)/2f,17,17),ink,1.6f);area.X+=30;area.Width-=30;}
            if(activity){area.X+=17;area.Width-=17;}
            TextRenderer.DrawText(g,Text,Font,area,ink,TextFormatFlags.HorizontalCenter|TextFormatFlags.VerticalCenter|TextFormatFlags.EndEllipsis|TextFormatFlags.SingleLine);
        }
        public void SetVisualForTest(string state){flash=0;ripple=1;over=state=="hover";down=state=="pressed";activity=state=="loading";Enabled=state!="disabled";if(state=="click"){origin=new PointF(Width/2f,Height/2f);ripple=0;}if(state=="success"||state=="error"){flash=1;flashColor=state=="success"?Color.FromArgb(39,166,126):Color.FromArgb(222,83,103);}for(int i=0;i<14;i++)Step(.016f);if(state=="click")ripple=.22f;}
        public void KeyboardDownForTest(){OnKeyDown(new KeyEventArgs(Keys.Space));for(int i=0;i<12;i++)Step(.016f);}
        public void KeyboardUpForTest(){OnKeyUp(new KeyEventArgs(Keys.Space));for(int i=0;i<30;i++)Step(.016f);}
        public void ClickForMotionTest(){OnClick(EventArgs.Empty);}
    }
    static class Glyphs {
        public static void Draw(Graphics g,string kind,RectangleF rect,Color color,float thickness){
            var save=g.Save();g.TranslateTransform(rect.X,rect.Y);g.ScaleTransform(rect.Width/20,rect.Height/20);
            using(var p=new Pen(color,thickness)){p.StartCap=p.EndCap=LineCap.Round;p.LineJoin=LineJoin.Round;
                if(kind=="download"){g.DrawLine(p,10,2,10,12);g.DrawLines(p,new[]{new PointF(6,8),new PointF(10,12),new PointF(14,8)});g.DrawLines(p,new[]{new PointF(3,12),new PointF(3,17),new PointF(17,17),new PointF(17,12)});}
                else if(kind=="progress"){g.DrawLine(p,4,4,4,16);g.DrawLine(p,4,16,17,16);g.DrawLines(p,new[]{new PointF(7,12),new PointF(10,8),new PointF(13,10),new PointF(17,4)});}
                else if(kind=="folder"){g.DrawLines(p,new[]{new PointF(2,5),new PointF(7,5),new PointF(9,7),new PointF(18,7),new PointF(16,16),new PointF(2,16),new PointF(2,5)});}
                else if(kind=="arrow"||kind=="external"){g.DrawLine(p,4,10,16,10);g.DrawLines(p,new[]{new PointF(12,6),new PointF(16,10),new PointF(12,14)});}
                else if(kind=="refresh"){g.DrawArc(p,3,3,14,14,30,285);g.DrawLines(p,new[]{new PointF(12,2),new PointF(17,3),new PointF(16,8)});}
                else if(kind=="help"){g.DrawEllipse(p,2,2,16,16);g.DrawArc(p,7,5,6,6,180,230);g.DrawLine(p,10,11,10,12);g.DrawLine(p,10,15,10,15.1f);}
                else if(kind=="eye"){g.DrawBezier(p,1,10,6,2,14,2,19,10);g.DrawBezier(p,1,10,6,18,14,18,19,10);g.DrawEllipse(p,7,7,6,6);}
                else if(kind=="user"){g.DrawEllipse(p,6,2,8,8);g.DrawArc(p,3,12,14,10,180,180);}
                else if(kind=="lock"){g.DrawArc(p,6,2,8,10,180,180);g.DrawRectangle(p,4,8,12,10);g.DrawLine(p,10,12,10,15);}
                else if(kind=="check"){g.DrawLines(p,new[]{new PointF(4,10),new PointF(8,14),new PointF(16,5)});}
                else if(kind=="close"){g.DrawLine(p,5,5,15,15);g.DrawLine(p,15,5,5,15);}
                else if(kind=="minimize")g.DrawLine(p,5,13,15,13);
                else if(kind=="maximize")g.DrawRectangle(p,5,5,10,10);
                else if(kind=="restore"){g.DrawLines(p,new[]{new PointF(7,4),new PointF(16,4),new PointF(16,13)});g.DrawRectangle(p,4,7,9,9);}
            }g.Restore(save);
        }
    }
    class ToolCard:SoftButton {
        public string Subtitle="";
        protected override void PaintContent(Graphics g,Rectangle area,Color ink,float hover){
            var iconBox=new RectangleF(area.Left+18,area.Top+(area.Height-40)/2f-hover*2,40,40);
            using(var path=Theme.Round(iconBox,12))using(var b=new SolidBrush(Color.FromArgb(235,247,251)))g.FillPath(b,path);
            Glyphs.Draw(g,Glyph,new RectangleF(iconBox.X+10,iconBox.Y+10,20,20),Theme.Cyan,1.5f);
            using(var f=new Font("Microsoft YaHei UI",10,FontStyle.Bold))TextRenderer.DrawText(g,Text,f,new Rectangle(area.X+72,area.Y+19,area.Width-110,25),Theme.Ink,TextFormatFlags.EndEllipsis|TextFormatFlags.SingleLine);
            using(var f=new Font("Microsoft YaHei UI",8))TextRenderer.DrawText(g,Subtitle,f,new Rectangle(area.X+72,area.Y+48,area.Width-88,24),Theme.Muted,TextFormatFlags.EndEllipsis|TextFormatFlags.SingleLine);
            Glyphs.Draw(g,"arrow",new RectangleF(area.Right-29+hover*3,area.Top+23,15,15),Theme.Cyan,1.5f);
        }
    }
    class WindowButton:SoftButton {
        readonly string action;readonly ToolTip tip=new ToolTip();
        public WindowButton(string action){this.action=action;Compact=true;AccessibleName=action=="close"?"关闭窗口":action=="minimize"?"最小化":"最大化或还原";tip.SetToolTip(this,AccessibleName);BackColor=Theme.Canvas;ForeColor=Theme.Muted;TabStop=true;}
        protected override void Dispose(bool disposing){if(disposing)tip.Dispose();base.Dispose(disposing);}
        protected override void PaintContent(Graphics g,Rectangle area,Color ink,float hover){
            if(action=="close")ink=MotionClock.Mix(ink,Theme.Coral,hover);
            string glyph=action=="maximize"&&FindForm()!=null&&FindForm().WindowState==FormWindowState.Maximized?"restore":action;
            Glyphs.Draw(g,glyph,new RectangleF(area.X+(area.Width-18)/2f,area.Y+(area.Height-18)/2f,18,18),ink,1.4f);
        }
        public void ClickForTest(){OnClick(EventArgs.Empty);}
    }
    class MotionInput:Panel,IMotion {
        readonly TextBox input;bool focus;float amount;
        public bool Alive {get{return !IsDisposed&&IsHandleCreated;}}
        public MotionInput(TextBox input,string glyph){this.input=input;Glyph=glyph;DoubleBuffered=true;BackColor=Color.White;Padding=new Padding(38,11,12,8);Margin=Padding.Empty;input.BorderStyle=BorderStyle.None;input.BackColor=Color.White;input.Font=new Font("Microsoft YaHei UI",10);input.Dock=DockStyle.Fill;Controls.Add(input);input.GotFocus+=delegate{focus=true;MotionClock.Wake(this);};input.LostFocus+=delegate{focus=false;MotionClock.Wake(this);};Click+=delegate{input.Focus();};}
        public string Glyph;
        protected override void Dispose(bool disposing){if(disposing)MotionClock.Forget(this);base.Dispose(disposing);}
        public bool Step(float dt){amount=MotionClock.Approach(amount,focus?1:0,dt);Invalidate();return Math.Abs(amount-(focus?1:0))>.003f;}
        protected override void OnPaintBackground(PaintEventArgs e){var g=e.Graphics;g.Clear(MotionClock.ParentColor(this));g.SmoothingMode=SmoothingMode.AntiAlias;using(var path=Theme.Round(new RectangleF(1,1,Width-3,Height-3),11))using(var b=new SolidBrush(Color.White))using(var p=new Pen(MotionClock.Mix(Color.FromArgb(222,229,239),Theme.Cyan,amount),1+amount*.5f)){g.FillPath(b,path);g.DrawPath(p,path);}Glyphs.Draw(g,Glyph,new RectangleF(12,(Height-17)/2f,17,17),MotionClock.Mix(Theme.Muted,Theme.Cyan,amount),1.4f);}
    }
    class MotionCheckBox:CheckBox,IMotion {
        bool over;float check,hover;
        public bool Alive {get{return !IsDisposed&&IsHandleCreated;}}
        public MotionCheckBox(){DoubleBuffered=true;SetStyle(ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer,true);Cursor=Cursors.Hand;}
        protected override void Dispose(bool disposing){if(disposing)MotionClock.Forget(this);base.Dispose(disposing);}
        protected override void OnCheckedChanged(EventArgs e){if(!IsHandleCreated)check=Checked?1:0;else MotionClock.Wake(this);base.OnCheckedChanged(e);}
        protected override void OnMouseEnter(EventArgs e){over=true;MotionClock.Wake(this);base.OnMouseEnter(e);}
        protected override void OnMouseLeave(EventArgs e){over=false;MotionClock.Wake(this);base.OnMouseLeave(e);}
        protected override void OnGotFocus(EventArgs e){Invalidate();base.OnGotFocus(e);}
        protected override void OnLostFocus(EventArgs e){Invalidate();base.OnLostFocus(e);}
        public bool Step(float dt){check=MotionClock.Approach(check,Checked?1:0,dt);hover=MotionClock.Approach(hover,over?1:0,dt);Invalidate();return Math.Abs(check-(Checked?1:0))>.003f||Math.Abs(hover-(over?1:0))>.003f;}
        protected override void OnPaint(PaintEventArgs e){var g=e.Graphics;g.Clear(MotionClock.ParentColor(this));g.SmoothingMode=SmoothingMode.AntiAlias;var rect=new RectangleF(2,(Height-15)/2f,15,15);using(var path=Theme.Round(rect,4))using(var b=new SolidBrush(MotionClock.Mix(Color.White,Theme.Cyan,check)))using(var p=new Pen(MotionClock.Mix(Color.FromArgb(196,211,222),Theme.Cyan,Math.Max(check,hover)))){g.FillPath(b,path);g.DrawPath(p,path);}if(check>.05f)Glyphs.Draw(g,"check",new RectangleF(rect.X+2,rect.Y+2,11,11),Color.FromArgb((int)(255*check),Color.White),2);TextRenderer.DrawText(g,Text,Font,new Rectangle(26,0,Width-26,Height),Enabled?ForeColor:Theme.Muted,TextFormatFlags.VerticalCenter|TextFormatFlags.EndEllipsis|TextFormatFlags.SingleLine);if(Focused&&ShowFocusCues)ControlPaint.DrawFocusRectangle(g,new Rectangle(24,3,Width-26,Height-6));}
    }
    static class MotionEffects {
        public static void Busy(Button button,bool busy){var animated=button as SoftButton;if(animated!=null)animated.Activity=busy;}
        public static void Progress(Button button,int value){var animated=button as SoftButton;if(animated!=null)animated.ProgressValue=value;}
        public static void Feedback(Button button,bool success){var animated=button as SoftButton;if(animated!=null)animated.Feedback(success);}
    }
}
