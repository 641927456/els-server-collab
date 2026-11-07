using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

static class StatusRefreshTests {
    static Type mainForm, launchMode, program;
    static string fixture;
    static readonly List<string> uiErrors = new List<string>();
    const BindingFlags Instance = BindingFlags.Instance|BindingFlags.NonPublic|BindingFlags.Public;
    const BindingFlags Static = BindingFlags.Static|BindingFlags.NonPublic|BindingFlags.Public;
    static FieldInfo Field(object obj,string name) {return obj.GetType().GetField(name,Instance);}
    static T Read<T>(object obj,string name) {return (T)Field(obj,name).GetValue(obj);}
    static void Set(object obj,string name,object value) {Field(obj,name).SetValue(obj,value);}
    static object Call(object obj,string name) {return obj.GetType().GetMethod(name,Instance).Invoke(obj,null);}
    static void Mode(bool local) {launchMode.GetField("Local",Static).SetValue(null,local);}
    static Dictionary<string,object> Reply(bool online) {return new Dictionary<string,object>{{"ok",online}};}
    static void Check(bool condition,string message) {if(!condition)throw new Exception(message);}
    static void PumpUntil(Func<bool> done,string message,int timeout=5000) {
        var clock=Stopwatch.StartNew();
        while(!done()&&clock.ElapsedMilliseconds<timeout){Application.DoEvents();Thread.Sleep(5);}
        Application.DoEvents();Check(done(),message);Check(uiErrors.Count==0,String.Join(";",uiErrors));
    }
    static void Pump(int milliseconds) {var clock=Stopwatch.StartNew();PumpUntil(()=>clock.ElapsedMilliseconds>=milliseconds,"Message loop did not advance",milliseconds+1000);}
    static Form NewForm() {
        Mode(false);
        var form=(Form)Activator.CreateInstance(mainForm,new object[]{true});
        IntPtr handle=form.Handle;
        Check(!form.Visible,"Test form became visible");
        return form;
    }
    static object PeriodicTransitions() {
        using(var form=NewForm()) {
            var label=Read<Label>(form,"server");var timer=Read<System.Windows.Forms.Timer>(form,"serverStatusTimer");
            Check(timer.Interval==10000,"Production polling interval differs");
            int state=1,calls=0,active=0,maximum=0;
            Set(form,"serverStatusQuery",(Func<string,string,Dictionary<string,object>>)((host,pin)=>{
                int count=Interlocked.Increment(ref active);maximum=Math.Max(maximum,count);Interlocked.Increment(ref calls);
                try {Thread.Sleep(70);int value=Volatile.Read(ref state);if(value<0)throw new IOException("fixture offline");return Reply(value==1);}
                finally {Interlocked.Decrement(ref active);}
            }));
            timer.Interval=25;timer.Start();
            PumpUntil(()=>label.Text.StartsWith("服务器在线"),"Initial timer check did not become online");
            Set(form,"busy",true);Interlocked.Exchange(ref state,-1);
            PumpUntil(()=>label.Text.StartsWith("暂时无法连接"),"Connection loss remained green");
            Check(label.ForeColor.ToArgb()==Color.FromArgb(238,106,90).ToArgb(),"Offline indicator is not red");
            int before=calls;Interlocked.Exchange(ref state,0);
            PumpUntil(()=>calls>before&&!Read<bool>(form,"checkingServerStatus"),"Negative status reply not observed");
            Check(label.Text.StartsWith("暂时无法连接"),"Negative status reply was accepted");
            Interlocked.Exchange(ref state,1);
            PumpUntil(()=>label.Text.StartsWith("服务器在线"),"Service recovery was not refreshed");
            Check(label.ForeColor.ToArgb()==Color.FromArgb(63,157,134).ToArgb(),"Recovered indicator is not green");
            Check(maximum==1,"Timer created overlapping status requests");
            timer.Stop();Set(form,"busy",false);
            return new {timer_detects_disconnect=true,timer_detects_recovery=true,negative_reply_rejected=true,refreshes_while_busy=true,maximum_concurrent_requests=maximum,production_interval_ms=10000};
        }
    }
    static object ModeChangeDuringRequest() {
        using(var form=NewForm())using(var entered=new ManualResetEventSlim())using(var release=new ManualResetEventSlim()) {
            int calls=0;bool localSeen=false;var paints=new List<string>();var label=Read<Label>(form,"server");
            label.TextChanged+=delegate{paints.Add(label.Text);};
            Set(form,"serverStatusQuery",(Func<string,string,Dictionary<string,object>>)((host,pin)=>{
                int call=Interlocked.Increment(ref calls);
                if(call==1){Check(host=="134.175.57.52","Initial endpoint differs");entered.Set();Check(release.Wait(3000),"Blocked request was not released");return Reply(true);}
                Check(host=="127.0.0.1"&&pin==new string('b',64),"Mode query used a mixed endpoint or certificate");localSeen=true;return Reply(false);
            }));
            var pending=(Task)Call(form,"RefreshServerStatus");PumpUntil(()=>entered.IsSet,"Initial query did not enter");
            Mode(true);Call(form,"RefreshSelectedServerStatus");Pump(100);
            Check(calls==1,"Selection refresh overlapped the old query");
            Check(label.Text.StartsWith("正在检查服务器"),"Old online label survived mode selection");
            release.Set();PumpUntil(()=>pending.IsCompleted&&localSeen,"Selected endpoint was not checked after old completion");pending.GetAwaiter().GetResult();
            Check(label.Text=="暂时无法连接 · 本机","Old server result overwrote the local status");
            Check(!paints.Contains("服务器在线 · 本机"),"Old response was painted as the selected endpoint");
            Mode(false);
            return new {in_flight_mode_switch=true,host_and_pin_captured_together=true,stale_response_discarded=true,selected_endpoint_checked_immediately_after_old_request=true};
        }
    }
    static object SameEndpointInvalidation() {
        using(var form=NewForm())using(var entered=new ManualResetEventSlim())using(var release=new ManualResetEventSlim()) {
            int calls=0;var paints=new List<string>();var label=Read<Label>(form,"server");label.TextChanged+=delegate{paints.Add(label.Text);};
            Set(form,"serverStatusQuery",(Func<string,string,Dictionary<string,object>>)((host,pin)=>{
                int call=Interlocked.Increment(ref calls);
                if(call==1){entered.Set();Check(release.Wait(3000),"Invalidated request was not released");return Reply(false);}
                return Reply(true);
            }));
            var pending=(Task)Call(form,"RefreshServerStatus");PumpUntil(()=>entered.IsSet,"Query did not start");
            Mode(true);Call(form,"RefreshSelectedServerStatus");Mode(false);Call(form,"RefreshSelectedServerStatus");
            release.Set();PumpUntil(()=>pending.IsCompleted,"Refreshed online observation did not finish");pending.GetAwaiter().GetResult();
            Check(calls==2&&label.Text.StartsWith("服务器在线"),"Same endpoint was not queried again after invalidation");
            Check(!paints.Exists(text=>text.StartsWith("暂时无法连接")),"Invalidated result was briefly painted");
            return new {online_local_online_race=true,invalidated_result_never_painted=true,invalidation_requests_fresh_observation=true};
        }
    }
    static object CloseDuringRequest() {
        var form=NewForm();
        using(var entered=new ManualResetEventSlim())using(var release=new ManualResetEventSlim()) {
            int calls=0;
            Set(form,"serverStatusQuery",(Func<string,string,Dictionary<string,object>>)((host,pin)=>{
                Interlocked.Increment(ref calls);entered.Set();Check(release.Wait(3000),"Closing query was not released");return Reply(true);
            }));
            var timer=Read<System.Windows.Forms.Timer>(form,"serverStatusTimer");timer.Interval=25;timer.Start();
            var pending=(Task)Call(form,"RefreshServerStatus");PumpUntil(()=>entered.IsSet,"Close fixture query did not start");
            form.Dispose();release.Set();PumpUntil(()=>pending.IsCompleted,"Closing form left its query pending");pending.GetAwaiter().GetResult();Pump(100);
            Check(form.IsDisposed&&calls==1,"Closed form continued polling");
            return new {close_during_request=true,timer_released=true,no_disposed_control_write=true,no_unhandled_ui_exception=true};
        }
    }
    static object PublicStatus() {
        var method=program.GetMethod("ServerStatus",Static);
        const string pin="d753047bea9c44a3319337732ed9e1bc8cf33d6cdb6001dd6aab254ba4bc14a6";
        var reply=(Dictionary<string,object>)method.Invoke(null,new object[]{"134.175.57.52",pin});
        Check(Object.Equals(reply["ok"],true),"Candidate could not read the real public status");
        bool rejected=false;
        try {method.Invoke(null,new object[]{"134.175.57.52",new string('0',64)});}
        catch(TargetInvocationException error){rejected=error.InnerException is System.Security.Authentication.AuthenticationException;}
        Check(rejected,"Wrong certificate pin was accepted");
        return new {actual_candidate_assembly=true,public_status_ok=true,incorrect_certificate_pin_rejected=true,no_account_credentials_sent=true};
    }
    static object StartupPolling() {
        using(var form=NewForm()) {
            int state=1,calls=0;
            Set(form,"serverStatusQuery",(Func<string,string,Dictionary<string,object>>)((host,pin)=>{Interlocked.Increment(ref calls);return Reply(Volatile.Read(ref state)==1);}));
            Set(form,"proofMode",false);
            typeof(Form).GetMethod("OnShown",BindingFlags.Instance|BindingFlags.NonPublic).Invoke(form,new object[]{EventArgs.Empty});
            var timer=Read<System.Windows.Forms.Timer>(form,"serverStatusTimer");var label=Read<Label>(form,"server");
            PumpUntil(()=>timer.Enabled&&label.Text.StartsWith("服务器在线")&&!Read<bool>(form,"checkingUpdate"),"Normal Shown handler did not start polling",15000);
            Check(timer.Interval==10000,"Normal startup changed polling cadence");
            Interlocked.Exchange(ref state,0);
            PumpUntil(()=>label.Text.StartsWith("暂时无法连接"),"Normal startup did not refresh after a real 10-second interval",12000);
            Check(!form.Visible,"Normal Shown test exposed a window");
            return new {normal_shown_callback=true,starts_polling_automatically=true,actual_ten_second_tick_observed=true,calls=calls,visible_window=false};
        }
    }
    [STAThread] static int Main(string[] args) {
        object report;
        try {
            Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
            Application.ThreadException+=delegate(object sender,ThreadExceptionEventArgs error){uiErrors.Add(error.Exception.ToString());};
            var assembly=Assembly.LoadFrom(args[0]);mainForm=assembly.GetType("ElsFriends.MainForm",true);launchMode=assembly.GetType("ElsFriends.LaunchMode",true);program=assembly.GetType("ElsFriends.Program",true);
            fixture=Path.GetFullPath(args[2]);Directory.CreateDirectory(fixture);program.GetField("DataRoot",Static).SetValue(null,fixture);
            string workspace=Path.Combine(fixture,"workspace"),state=Path.Combine(workspace,"state","unified-server");Directory.CreateDirectory(state);
            File.WriteAllText(Path.Combine(state,"endpoint.json"),"{\"certificate_sha256\":\""+new string('b',64)+"\"}");launchMode.GetField("LocalRoot",Static).SetValue(null,workspace);
            SynchronizationContext.SetSynchronizationContext(new WindowsFormsSynchronizationContext());
            if(args.Length>3&&args[3]=="startup")report=new {ok=true,startup=StartupPolling(),game_started=false,user_settings_changed=false};
            else report=new {ok=true,periodic=PeriodicTransitions(),mode_change=ModeChangeDuringRequest(),invalidation=SameEndpointInvalidation(),close=CloseDuringRequest(),public_status=PublicStatus(),game_started=false,user_settings_changed=false};
        } catch(Exception error) {report=new {ok=false,error=error.ToString()};}
        string json=new JavaScriptSerializer().Serialize(report);File.WriteAllText(args[1],json);Console.WriteLine(json);
        return json.Contains("\"ok\":true")?0:1;
    }
}
