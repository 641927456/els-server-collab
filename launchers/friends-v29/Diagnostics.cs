using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.Diagnostics;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

namespace ElsFriends {
    class DiagnosticAttempt {
        public string Id, Label;
        public override string ToString(){return Label;}
    }
    class DiagnosticBundle {
        public string Archive, Classification;
        public string RequestId,AttemptId,Description;
        public string[] Files=new string[0], Omissions=new string[0];
        public long Bytes,ExpandedBytes;
    }
    class DiagnosticsForm:ProofForm {
        protected override bool WindowResizable {get{return false;}}
        readonly ComboBox attempts=new ComboBox();readonly TextBox note=new TextBox(),files=new TextBox();
        readonly Label status=new Label();readonly Button generate=new SoftButton(),upload=new SoftButton(),export=new SoftButton();
        readonly Func<string,string,Task<DiagnosticBundle>> collect;
        readonly Func<DiagnosticBundle,Task<string>> submit;
        readonly bool uploadAvailable;bool working;DiagnosticBundle bundle;string reportId;
        public DiagnosticsForm(IEnumerable<DiagnosticAttempt> choices,Func<string,string,Task<DiagnosticBundle>> collect,Func<DiagnosticBundle,Task<string>> submit,bool uploadAvailable,bool test=false){
            this.collect=collect;this.submit=submit;this.uploadAvailable=uploadAvailable;proofMode=test;
            Text="诊断与反馈";ClientSize=new Size(760,674);MinimumSize=new Size(600,580);FormBorderStyle=FormBorderStyle.None;
            StartPosition=FormStartPosition.CenterParent;ShowInTaskbar=false;BackColor=Theme.Canvas;ForeColor=Theme.Ink;Font=new Font("Microsoft YaHei UI",9);AutoScaleMode=AutoScaleMode.Dpi;
            var outer=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=1,RowCount=2,Padding=Padding.Empty,Margin=Padding.Empty};outer.RowStyles.Add(new RowStyle(SizeType.Absolute,45));outer.RowStyles.Add(new RowStyle(SizeType.Percent,100));Controls.Add(outer);
            var header=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=2,Padding=new Padding(22,6,8,6),BackColor=Color.White,Margin=Padding.Empty};header.RowStyles.Add(new RowStyle(SizeType.Percent,100));header.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));header.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,38));
            var title=new Label {Text="E L R I O S    /    诊断与反馈",Dock=DockStyle.Fill,TextAlign=ContentAlignment.MiddleLeft,ForeColor=Theme.Muted};header.Controls.Add(title,0,0);header.Controls.Add(WindowControls(false),1,0);outer.Controls.Add(header,0,0);BindWindowDrag(header);BindWindowDrag(title);
            var scroll=new Panel {Dock=DockStyle.Fill,AutoScroll=true,Padding=new Padding(22,16,22,15),Margin=Padding.Empty};outer.Controls.Add(scroll,0,1);
            var layout=new TableLayoutPanel {Dock=DockStyle.Top,Height=584,ColumnCount=1,RowCount=11,Margin=Padding.Empty};foreach(int h in new[]{38,48,23,34,24,66,38,170,31,49,58})layout.RowStyles.Add(new RowStyle(SizeType.Absolute,h));scroll.Controls.Add(layout);
            layout.Controls.Add(new Label {Text="把这次问题，完整地告诉我们。",Dock=DockStyle.Fill,Font=new Font(Font.FontFamily,18,FontStyle.Bold)},0,0);
            layout.Controls.Add(new Label {Text="只收集所选启动的诊断日志、版本摘要和对应时段的系统错误。\n不包含密码、登录令牌、存档、截图、内存文件或游戏资源。",Dock=DockStyle.Fill,ForeColor=Theme.Muted},0,1);
            layout.Controls.Add(new Label {Text="选择这次启动",Dock=DockStyle.Fill},0,2);
            attempts.DropDownStyle=ComboBoxStyle.DropDownList;attempts.Dock=DockStyle.Fill;attempts.AccessibleName="选择诊断启动记录";foreach(var item in choices)attempts.Items.Add(item);if(attempts.Items.Count>0)attempts.SelectedIndex=0;layout.Controls.Add(attempts,0,3);
            layout.Controls.Add(new Label {Text="当时发生了什么？（可选，请勿填写密码）",Dock=DockStyle.Fill,Padding=new Padding(0,3,0,0)},0,4);
            note.Multiline=true;note.MaxLength=2000;note.Dock=DockStyle.Fill;note.ScrollBars=ScrollBars.Vertical;note.AccessibleName="问题描述";layout.Controls.Add(note,0,5);
            generate.Text="生成并预览诊断包";generate.Dock=DockStyle.Fill;generate.BackColor=Theme.Coral;generate.ForeColor=Color.White;generate.Click+=async delegate {await Generate();};layout.Controls.Add(generate,0,6);
            files.Multiline=true;files.ReadOnly=true;files.Dock=DockStyle.Fill;files.ScrollBars=ScrollBars.Vertical;files.Font=new Font("Consolas",9);files.Text="生成后，这里会列出实际包含的文件与压缩大小。\r\n查看清单后，你可以上传，也可以先保存到本地。";files.AccessibleName="诊断包文件清单";layout.Controls.Add(files,0,7);
            status.Dock=DockStyle.Fill;status.ForeColor=Theme.Muted;status.Padding=new Padding(0,5,0,0);status.Text="诊断生成或上传失败，不会影响游戏。";layout.Controls.Add(status,0,8);
            var actions=new TableLayoutPanel {Dock=DockStyle.Fill,ColumnCount=2,Margin=Padding.Empty};actions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,58));actions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,42));
            upload.Text="上传这份诊断";upload.Dock=DockStyle.Fill;upload.BackColor=Theme.Coral;upload.ForeColor=Color.White;upload.Enabled=false;upload.Margin=new Padding(0,0,12,0);upload.Click+=async delegate {await Upload();};actions.Controls.Add(upload,0,0);
            export.Text="保存诊断包…";export.Dock=DockStyle.Fill;export.BackColor=Color.White;export.ForeColor=Theme.Cyan;export.Enabled=false;export.Click+=delegate {Export();};actions.Controls.Add(export,1,0);layout.Controls.Add(actions,0,9);
            layout.Controls.Add(new Label {Text=uploadAvailable?"上传成功后会显示报告编号，房主可直接读取并结合服务器日志排查。\n只有你点击上传，诊断包才会发送到朋友服。":"登录后可上传；当前仍可生成诊断包并保存到本地。\n只有你点击上传，诊断包才会发送到朋友服。",Dock=DockStyle.Fill,Padding=new Padding(0,8,0,0),ForeColor=Theme.Muted,Font=new Font(Font.FontFamily,8)},0,10);
            note.TextChanged+=delegate {InvalidateBundle();};attempts.SelectedIndexChanged+=delegate {InvalidateBundle();};
            FormClosing+=delegate(object sender,FormClosingEventArgs e){if(working){e.Cancel=true;status.Text="正在完成诊断操作，请稍候。";}};
        }
        void InvalidateBundle(){if(bundle!=null){bundle=null;reportId=null;upload.Text="上传这份诊断";upload.Enabled=export.Enabled=false;status.Text="内容已改变，请重新生成诊断包。";}}
        void Busy(bool value){working=value;attempts.Enabled=note.Enabled=generate.Enabled=!value;upload.Enabled=!value&&bundle!=null&&uploadAvailable;export.Enabled=!value&&bundle!=null;}
        async Task Generate(){
            if(working||attempts.SelectedItem==null)return;MotionEffects.Busy(generate,true);Busy(true);status.Text="正在收集本次记录、脱敏并压缩…";
            try{
                bundle=await collect(((DiagnosticAttempt)attempts.SelectedItem).Id,note.Text);
                files.Text="压缩后 "+(bundle.Bytes/1024.0).ToString("0.0")+" KiB / 原始文本 "+(bundle.ExpandedBytes/1024.0).ToString("0.0")+" KiB\r\n\r\n"+String.Join("\r\n",bundle.Files);
                if(bundle.Omissions.Length>0)files.AppendText("\r\n未收集："+String.Join("、",bundle.Omissions));
                status.Text=bundle.Classification??"已生成，请查看清单后上传或保存。";MotionEffects.Feedback(generate,true);
            }catch {bundle=null;MotionEffects.Feedback(generate,false);status.Text="诊断包生成未完成，请稍后重试；游戏不受影响。";}
            finally{MotionEffects.Busy(generate,false);Busy(false);}
        }
        async Task Upload(){
            if(working||bundle==null||!uploadAvailable)return;
            if(reportId!=null){Clipboard.SetText(reportId);status.Text="报告编号已复制："+reportId;return;}
            MotionEffects.Busy(upload,true);Busy(true);status.Text="正在加密上传，请稍候…";
            try {reportId=await submit(bundle);status.Text="上传成功 · 报告编号："+reportId;upload.Text="复制报告编号";MotionEffects.Feedback(upload,true);}
            catch {MotionEffects.Feedback(upload,false);status.Text="上传未完成，诊断包仍保留在本地，可重试或保存。";}
            finally{MotionEffects.Busy(upload,false);Busy(false);}
        }
        void Export(){if(bundle==null||working)return;using(var dialog=new SaveFileDialog {Filter="诊断压缩包 (*.zip)|*.zip",FileName=Path.GetFileName(bundle.Archive)}){if(dialog.ShowDialog(this)!=DialogResult.OK)return;try{File.Copy(bundle.Archive,dialog.FileName,true);status.Text="诊断包已保存。";MotionEffects.Feedback(export,true);}catch{status.Text="无法保存到所选位置，请换一个目录。";}}}
        public async Task<object> VerifyForTest(){await Generate();if(bundle==null||!upload.Enabled||!export.Enabled)throw new Exception("Report generation controls");await Upload();if(!status.Text.Contains("D20261016-fixture"))throw new Exception("Report ID missing");return new {generated=true,preview_files=true,explicit_upload=true,report_id_visible=true,export_available=export.Enabled};}
    }
    static class DiagnosticService {
        static JavaScriptSerializer Json(){return new JavaScriptSerializer();}
        static string AttemptPath(string id){if(!Regex.IsMatch(id??"","^[a-f0-9]{32}$"))throw new IOException("Invalid attempt");return Path.Combine(Program.DataRoot,"logs","attempts",id);}
        public static string BeginAttempt(){
            try {string id=Guid.NewGuid().ToString("N");Program.PrivateWrite(Path.Combine(AttemptPath(id),"attempt.json"),Json().Serialize(new Dictionary<string,object>{{"schema",1},{"attempt_id",id},{"started_utc",DateTimeOffset.UtcNow.ToString("o")},{"payload",Program.PayloadHash},{"phase","starting"}}));return id;}
            catch{return null;}
        }
        public static void Update(string id,string phase,int? code=null,bool ended=false){
            if(id==null)return;
            try {string path=Path.Combine(AttemptPath(id),"attempt.json");var value=Json().Deserialize<Dictionary<string,object>>(File.ReadAllText(path,Encoding.UTF8));value["phase"]=phase;if(code.HasValue)value["exit_code"]=code.Value;if(ended)value["ended_utc"]=DateTimeOffset.UtcNow.ToString("o");Program.PrivateWrite(path,Json().Serialize(value));}catch{}
        }
        public static string LogPath(string id,string name){return Path.Combine(id==null?Path.Combine(Program.DataRoot,"logs"):AttemptPath(id),name);}
        public static DiagnosticAttempt[] Choices(){
            var values=new List<DiagnosticAttempt>();string folder=Path.Combine(Program.DataRoot,"logs","attempts");
            if(Directory.Exists(folder))foreach(string path in Directory.GetDirectories(folder).OrderByDescending(Directory.GetLastWriteTimeUtc).Take(10)){
                string id=Path.GetFileName(path);if(!Regex.IsMatch(id,"^[a-f0-9]{32}$"))continue;
                try{var meta=Json().Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(path,"attempt.json"),Encoding.UTF8));DateTimeOffset at;string time=DateTimeOffset.TryParse(Convert.ToString(meta["started_utc"]),out at)?at.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss"):"时间未知";string phase=Convert.ToString(meta["phase"]);var names=new Dictionary<string,string>{{"starting","准备中"},{"login","登录中"},{"authentication_failed","登录未通过"},{"preflight","预检查中"},{"preflight_failed","预检查未通过"},{"game_running","游戏运行中"},{"game_exit","游戏已退出"},{"game_failed","启动或游戏返回非零状态"},{"launcher_error","启动器错误"},{"client_not_selected","未选择客户端"},{"credentials_missing","未填写登录信息"}};values.Add(new DiagnosticAttempt {Id=id,Label=time+" · "+(names.ContainsKey(phase)?names[phase]:"启动记录")+(meta.ContainsKey("exit_code")?" · 状态 "+meta["exit_code"]:"")});}catch{}
            }
            if(values.Count==0)values.Add(new DiagnosticAttempt {Id=null,Label="最近一次启动 · 旧版日志（关联信息可能不完整）"});
            return values.ToArray();
        }
        static Dictionary<string,object> Request(string root,string attempt,string description,string client,string name,string token,string requestId){
            string payload=root;
            if(attempt!=null)try{var meta=Json().Deserialize<Dictionary<string,object>>(File.ReadAllText(Path.Combine(AttemptPath(attempt),"attempt.json"),Encoding.UTF8));string value=Convert.ToString(meta["payload"]);if(Regex.IsMatch(value,"^[a-f0-9]{64}$"))payload=Path.Combine(Program.DataRoot,"versions",value.Substring(0,16));}catch{}
            return new Dictionary<string,object>{{"data_root",Program.DataRoot},{"payload_root",payload},{"attempt_id",attempt},{"description",description},{"client_path",client},{"name",name??""},{"token",token??""},{"host",Program.Host},{"port",19400},{"certificate_sha256",Program.Pin},{"request_id",requestId}};
        }
        static Dictionary<string,object> Run(string root,string action,Dictionary<string,object> request,string archive){
            string id=Guid.NewGuid().ToString("N"),folder=Path.Combine(Program.DataRoot,"diagnostics","operations");string input=Path.Combine(Program.DataRoot,"sessions","diagnostic-"+id+".json"),receipt=Path.Combine(folder,id+".json");
            try {
                Program.PrivateWrite(receipt,"{}");Program.PrivateWrite(input,Json().Serialize(request));
                string args="-X utf8 "+Program.Quote(Path.Combine(root,"tools","friends_diagnostics.py"))+" "+action+" --request "+Program.Quote(input)+(action=="collect"?" --output ":" --archive ")+Program.Quote(archive)+" --receipt "+Program.Quote(receipt);
                var info=new ProcessStartInfo(Path.Combine(root,"python","python.exe"),args){UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=root,RedirectStandardOutput=true,RedirectStandardError=true};
                using(var process=new Process()){process.StartInfo=info;process.OutputDataReceived+=delegate{};process.ErrorDataReceived+=delegate{};process.Start();process.BeginOutputReadLine();process.BeginErrorReadLine();if(!process.WaitForExit(70000)){process.Kill();process.WaitForExit();throw new IOException("Diagnostic helper timed out");}process.WaitForExit();}
                if(new FileInfo(receipt).Length>1024*1024)throw new IOException("Diagnostic receipt size");
                var result=Json().Deserialize<Dictionary<string,object>>(File.ReadAllText(receipt,Encoding.UTF8));if(!result.ContainsKey("ok")||!Object.Equals(result["ok"],true)||result.ContainsKey("upload_failed"))throw new IOException("Diagnostic operation did not complete");return result;
            }finally{try{if(File.Exists(input))File.Delete(input);}catch{} }
        }
        static string[] Strings(object value){var list=value as System.Collections.IEnumerable;if(list==null)return new string[0];var result=new List<string>();foreach(object item in list)result.Add(Convert.ToString(item));return result.ToArray();}
        public static Task<DiagnosticBundle> Generate(string root,string attempt,string description,string client,string name,string token){return Task.Run(()=>{
            string id=Guid.NewGuid().ToString("N"),folder=Path.Combine(Program.DataRoot,"diagnostics","outgoing");Program.PrivateWrite(Path.Combine(folder,".private"),"");string archive=Path.Combine(folder,id+".zip");
            var result=Run(root,"collect",Request(root,attempt,description,client,name,token,id),archive);string reason="请查看清单后上传或保存。";
            if(result.ContainsKey("classification")){var classification=result["classification"] as Dictionary<string,object>;if(classification!=null&&classification.ContainsKey("reason"))reason=Convert.ToString(classification["reason"]);}
            return new DiagnosticBundle {Archive=archive,RequestId=id,AttemptId=attempt,Description=description,Files=Strings(result["files"]),Omissions=Strings(result["omissions"]),Bytes=Convert.ToInt64(result["bytes"]),ExpandedBytes=Convert.ToInt64(result["expanded_bytes"]),Classification=reason};
        });}
        public static Task<string> Upload(string root,DiagnosticBundle bundle,string client,string name,string token){return Task.Run(()=>{
            var result=Run(root,"send",Request(root,bundle.AttemptId,bundle.Description,client,name,token,bundle.RequestId),bundle.Archive);var upload=result["upload"] as Dictionary<string,object>;string id=upload==null?"":Convert.ToString(upload["report_id"]);if(!Regex.IsMatch(id,"^D[0-9]{8}-[a-f0-9]{16}$"))throw new IOException("Diagnostic report ID missing");return id;
        });}
    }
}
