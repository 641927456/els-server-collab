using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace ElsFriends {
    static class DesignProof {
        static IEnumerable<Control> Children(Control root){foreach(Control control in root.Controls){yield return control;foreach(var child in Children(control))yield return child;}}
        static string Digest(Bitmap bitmap){using(var bytes=new MemoryStream()){bitmap.Save(bytes,System.Drawing.Imaging.ImageFormat.Png);return Program.Hex(SHA256.Create().ComputeHash(bytes.ToArray()));}}
        static void Settle(Control root){foreach(var button in Children(root).OfType<SoftButton>())button.SettleForTest();}
        static Bitmap PaintOnOldBuffer(Control control,Color color){
            var bitmap=new Bitmap(control.Width,control.Height);
            using(var g=Graphics.FromImage(bitmap)){
                g.Clear(color);g.SetClip(control.ClientRectangle);var args=new PaintEventArgs(g,control.ClientRectangle);
                var flags=System.Reflection.BindingFlags.NonPublic|System.Reflection.BindingFlags.Instance;
                if(control is Wordmark)control.GetType().GetMethod("OnPaintBackground",flags).Invoke(control,new object[]{args});
                control.GetType().GetMethod("OnPaint",flags).Invoke(control,new object[]{args});
            }
            return bitmap;
        }
        static object HeaderRepaint(MainForm form){
            var header=Children(form).Single(c=>c.AccessibleName=="半透明标题栏");int controls=0,pixels=0;
            foreach(var control in Children(header).Where(c=>c is SoftButton||c is Wordmark)){
                var button=control as SoftButton;if(button!=null)button.SettleForTest();
                using(var first=PaintOnOldBuffer(control,Color.Magenta))using(var second=PaintOnOldBuffer(control,Color.Lime)){
                    for(int y=0;y<control.Height;y++)for(int x=0;x<control.Width;x++){
                        if(first.GetPixel(x,y).ToArgb()!=second.GetPixel(x,y).ToArgb())throw new Exception("Header retained old buffer pixels: "+control.GetType().Name);
                        pixels++;
                    }
                }
                controls++;
            }
            return new {controls=controls,pixels_compared=pixels,old_buffer_independent=true,ghost_pixels=0};
        }
        static int EdgeDifference(Bitmap image){
            int error=0;Func<Color,Color,int> difference=(a,b)=>Math.Max(Math.Abs(a.R-b.R),Math.Max(Math.Abs(a.G-b.G),Math.Abs(a.B-b.B)));
            for(int i=0;i<5;i++){
                var left=image.GetPixel(i,image.Height/2);var right=image.GetPixel(image.Width-1-i,image.Height/2);
                var top=image.GetPixel(image.Width/2,i);var bottom=image.GetPixel(image.Width/2,image.Height-1-i);
                error=Math.Max(error,Math.Max(difference(left,right),Math.Max(difference(top,bottom),difference(left,top))));
            }
            return error;
        }
        static object VerifyBorders(){
            int worst=0,cases=0;
            foreach(var size in new[]{new Size(222,48),new Size(221,47)})
            using(var button=new SoftButton {Size=size,Text="",Quiet=true,Selected=true}){
                IntPtr handle=button.Handle;
                foreach(string state in new[]{"idle","hover","pressed","click"}){
                    button.SetVisualForTest(state);using(var bitmap=new Bitmap(size.Width,size.Height)){
                        button.DrawToBitmap(bitmap,new Rectangle(Point.Empty,size));int error=EdgeDifference(bitmap);
                        if(error>2)throw new Exception("Uneven button outline: "+size+"/"+state+"/"+error);worst=Math.Max(worst,error);cases++;
                    }
                }
            }
            return new {rendered_cases=cases,odd_and_even_sizes=true,all_four_edges_compared=true,maximum_channel_difference=worst};
        }
        static List<object> Buttons(ProofForm form,string name,string folder){
            var output=new List<object>();int index=0;
            foreach(var button in Children(form).OfType<Button>()) {
                var animated=button as SoftButton;if(animated==null)throw new Exception("Button without motion: "+name);
                bool enabled=button.Enabled;int count=0;var hashes=new Dictionary<string,string>();
                foreach(var state in new[]{"idle","hover","pressed","click","loading","disabled","success","error"}) {
                    animated.SetVisualForTest(state);using(var frame=new Bitmap(button.Width,button.Height)){button.DrawToBitmap(frame,new Rectangle(Point.Empty,frame.Size));hashes[state]=Digest(frame);frame.Save(Path.Combine(folder,name+"-"+index+"-"+state+".png"));}count++;
                }
                if(hashes["idle"]==hashes["hover"]||hashes["idle"]==hashes["pressed"]||hashes["idle"]==hashes["click"]||hashes["idle"]==hashes["disabled"]||hashes["idle"]==hashes["loading"])throw new Exception("Missing distinct button feedback: "+name+"/"+index);
                animated.SetVisualForTest("idle");animated.Enabled=enabled;animated.Activity=false;
                output.Add(new {surface=name,index=index,label=String.IsNullOrEmpty(button.AccessibleName)?button.Text:button.AccessibleName,states=count,hover_distinct=true,press_distinct=true,click_distinct=true,loading_distinct=true,disabled_distinct=true});index++;
            }
            return output;
        }
        static int Bounds(ProofForm form){
            int count=0;foreach(var button in Children(form).OfType<Button>()) {
                if(button.Width<27||button.Height<27)throw new Exception("Button too small: "+button.Text);
                for(Control control=button;control.Parent!=null;control=control.Parent)if(!control.Parent.ClientRectangle.Contains(control.Bounds))throw new Exception("Button clipped: "+button.Text+" in "+control.Parent.GetType().Name);
                if(!button.TabStop)throw new Exception("Button missing keyboard navigation");count++;
            }return count;
        }
        static void CheckRequiredCopy(MainForm form){
            var dc=Children(form).OfType<Button>().Single(c=>c.Name=="discord-community");var notice=Children(form).OfType<Label>().Single(c=>c.Name=="project-notice");
            if(dc.Text!="加入 DC 交流频道"||notice.Text!=MainForm.ProjectNotice||notice.Font.Size<10)throw new Exception("Community or project notice missing");
            var measured=TextRenderer.MeasureText(notice.Text,notice.Font,new Size(notice.Width,int.MaxValue),TextFormatFlags.WordBreak);
            if(measured.Height>notice.Height)throw new Exception("Project notice text clipped");
        }
        public static object Run(string directory){
            Directory.CreateDirectory(directory);string buttons=Path.Combine(directory,"buttons");Directory.CreateDirectory(buttons);var states=new List<object>();int count;object glassMaterials=null,headerRepaint=null;object outlines=VerifyBorders();
            using(var main=new MainForm(true)) {
                main.Snapshot(Path.Combine(directory,"main.png"));count=Bounds(main);CheckRequiredCopy(main);headerRepaint=HeaderRepaint(main);main.VerifyLauncherUxForTest();
                Settle(main);main.AccountForDesignTest(true);main.Snapshot(Path.Combine(directory,"account.png"));Bounds(main);main.AccountForDesignTest(false);
                Settle(main);main.SettingsForDesignTest(true);main.Snapshot(Path.Combine(directory,"settings.png"));Bounds(main);glassMaterials=main.VerifyGlassForDesignTest();states.AddRange(Buttons(main,"main",buttons));main.SettingsForDesignTest(false);Settle(main);
                main.ClientSize=main.MinimumSize;main.Snapshot(Path.Combine(directory,"main-minimum.png"));Bounds(main);CheckRequiredCopy(main);
                main.ClientSize=new Size(1440,900);main.Snapshot(Path.Combine(directory,"main-large.png"));Bounds(main);CheckRequiredCopy(main);
            }
            using(var registration=new RegisterForm("")){registration.Snapshot(Path.Combine(directory,"register.png"));Bounds(registration);var submit=Children(registration).OfType<Button>().Single(b=>b.AccessibleName=="创建账号并登录");if(submit.Height>54||submit.Width>202||submit.Height<36)throw new Exception("Registration confirmation was stretched");states.AddRange(Buttons(registration,"register",buttons));}
            using(var recovery=new TutorialRecoveryForm("fixture_only","fixture_only",true)){recovery.Snapshot(Path.Combine(directory,"recovery.png"));Bounds(recovery);states.AddRange(Buttons(recovery,"recovery",buttons));}
            using(var diagnostics=new DiagnosticsForm(new[]{new DiagnosticAttempt {Id="00000000000000000000000000000001",Label="测试启动记录"}},(id,note)=>Task.FromResult(new DiagnosticBundle {Archive="fixture.zip",Bytes=1024,ExpandedBytes=2048,Files=new[]{"版本摘要.json","启动日志.txt"}}),bundle=>Task.FromResult("D20261016-fixture"),true,true)) {
                diagnostics.Snapshot(Path.Combine(directory,"diagnostics.png"));Bounds(diagnostics);states.AddRange(Buttons(diagnostics,"diagnostics",buttons));
            }
            int clicks=0;using(var test=new SoftButton {Size=new Size(280,48),Text="登录并开始冒险",BackColor=Theme.Coral,ForeColor=Color.White,Font=new Font("Microsoft YaHei UI",11,FontStyle.Bold)}) {
                IntPtr handle=test.Handle;test.Click+=delegate{clicks++;};test.KeyboardDownForTest();if(test.PressAmount<.7f)throw new Exception("Keyboard press feedback absent");test.KeyboardUpForTest();if(test.PressAmount>.01f)throw new Exception("Keyboard release did not settle");
                int keyboardClicks=clicks;if(keyboardClicks!=1)throw new Exception("Keyboard activation missing or duplicated");
                test.Enabled=false;test.ClickForMotionTest();if(clicks!=keyboardClicks)throw new Exception("Disabled button invoked action");test.Enabled=true;test.Activity=true;test.ClickForMotionTest();if(clicks!=keyboardClicks)throw new Exception("Busy button invoked action");test.Activity=false;test.ClickForMotionTest();if(clicks!=keyboardClicks+1)throw new Exception("Ready button lost click action");
                string reduced=Environment.GetEnvironmentVariable("ELS_REDUCE_MOTION");try{Environment.SetEnvironmentVariable("ELS_REDUCE_MOTION","1");test.SetVisualForTest("hover");if(test.HoverAmount!=1)throw new Exception("Reduced motion not respected");}finally{Environment.SetEnvironmentVariable("ELS_REDUCE_MOTION",reduced);}
            }
            if(MotionClock.ActiveCount!=0)throw new Exception("Disposed controls retained by animation clock");
            return new {ok=true,main_buttons=count,animated_buttons_all_surfaces=states.Count,button_states=states,default_minimum_large_layout_unclipped=true,keyboard_press_and_release=true,disabled_and_busy_actions_blocked=true,reduced_motion_supported=true,animation_timers_disposed=true,rendering_without_activation=true,settings_open_and_escape_close=true,account_open_and_escape_close=true,account_accept_button_returns_to_home=true,missing_client_opens_directory_settings=true,missing_credentials_opens_account=true,validation_stops_before_network_or_game=true,busy_mode_and_source_controls_blocked=true,login_fields_enlarged=true,read_only_directory_not_a_tab_stop=true,glass_materials=glassMaterials,header_repaint=headerRepaint,outlines=outlines,dc_invite_text_visible=true,project_notice_complete_and_readable=true,friend_server_logo_embedded=true,game_or_real_accounts_accessed=false};
        }
    }
}
