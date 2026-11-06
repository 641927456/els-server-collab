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
        static List<object> Buttons(ProofForm form,string name,string folder){
            var output=new List<object>();int index=0;
            foreach(var button in Children(form).OfType<Button>()) {
                var animated=button as SoftButton;if(animated==null)throw new Exception("Button without motion: "+name);
                bool enabled=button.Enabled;int count=0;var hashes=new Dictionary<string,string>();
                foreach(var state in new[]{"idle","hover","pressed","click","loading","disabled","success","error"}) {
                    animated.SetVisualForTest(state);using(var frame=new Bitmap(button.Width,button.Height)){button.DrawToBitmap(frame,new Rectangle(Point.Empty,frame.Size));hashes[state]=Digest(frame);frame.Save(Path.Combine(folder,name+"-"+index+"-"+state+".png"));}count++;
                }
                if(hashes["idle"]==hashes["hover"]||hashes["idle"]==hashes["pressed"]||hashes["idle"]==hashes["disabled"]||hashes["idle"]==hashes["loading"])throw new Exception("Missing distinct button feedback: "+name+"/"+index);
                animated.SetVisualForTest("idle");animated.Enabled=enabled;animated.Activity=false;
                output.Add(new {surface=name,index=index,label=String.IsNullOrEmpty(button.AccessibleName)?button.Text:button.AccessibleName,states=count,hover_distinct=true,press_distinct=true,loading_distinct=true,disabled_distinct=true});index++;
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
        public static object Run(string directory){
            Directory.CreateDirectory(directory);string buttons=Path.Combine(directory,"buttons");Directory.CreateDirectory(buttons);var states=new List<object>();int count;
            using(var main=new MainForm(true)) {
                main.Snapshot(Path.Combine(directory,"main.png"));count=Bounds(main);states.AddRange(Buttons(main,"main",buttons));
                main.ClientSize=main.MinimumSize;main.Snapshot(Path.Combine(directory,"main-minimum.png"));Bounds(main);
                main.ClientSize=new Size(1440,900);main.Snapshot(Path.Combine(directory,"main-large.png"));Bounds(main);
            }
            using(var registration=new RegisterForm("")){registration.Snapshot(Path.Combine(directory,"register.png"));Bounds(registration);var submit=Children(registration).OfType<Button>().Single(b=>b.AccessibleName=="创建账号并登录");if(submit.Height>44||submit.Width>202||submit.Height<36)throw new Exception("Registration confirmation was stretched");states.AddRange(Buttons(registration,"register",buttons));}
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
            return new {ok=true,main_buttons=count,animated_buttons_all_surfaces=states.Count,button_states=states,default_minimum_large_layout_unclipped=true,keyboard_press_and_release=true,disabled_and_busy_actions_blocked=true,reduced_motion_supported=true,animation_timers_disposed=true,rendering_without_activation=true,game_or_real_accounts_accessed=false};
        }
    }
}
