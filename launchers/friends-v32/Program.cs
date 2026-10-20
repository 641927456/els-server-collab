using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net.Security;
using System.Net.Sockets;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace ElsFriends {
    static class Program {
        public const string Host = "134.175.57.52";
        public const string Pin = "d753047bea9c44a3319337732ed9e1bc8cf33d6cdb6001dd6aab254ba4bc14a6";
        public const string PayloadHash = "7d2f7db2c07b9da8302d1278bb80d4070c97bcddc03dd0ac80765aa03a129860";
        public static string DataRoot = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ElsFriends");
        public static JavaScriptSerializer Json = new JavaScriptSerializer();
        public static bool SettingsRecovered;
        static readonly byte[] Entropy = Encoding.UTF8.GetBytes("ElsFriends remembered login v1");
        public static string Hex(byte[] bytes) { return BitConverter.ToString(bytes).Replace("-", "").ToLowerInvariant(); }
        public static string Hash(Stream stream) { using (var sha = SHA256.Create()) return Hex(sha.ComputeHash(stream)); }
        public static string Quote(string text) {
            var b = new StringBuilder("\""); int slashes = 0;
            foreach (char c in text) { if (c == '\\') { slashes++; continue; } if (c == '"') b.Append('\\', slashes * 2 + 1); else b.Append('\\', slashes); b.Append(c); slashes = 0; }
            b.Append('\\', slashes * 2); return b.Append('"').ToString();
        }
        public static byte[] Exact(Stream s, int count) { byte[] b = new byte[count]; int i = 0; while (i < count) { int n = s.Read(b, i, count-i); if (n == 0) throw new IOException("Connection closed"); i += n; } return b; }
        public static Dictionary<string, object> Api(Dictionary<string, object> request) {
            var json = new JavaScriptSerializer();
            using (var tcp = new TcpClient()) {
                var connect = tcp.ConnectAsync(Host, 19400);
                if (!connect.Wait(8000)) throw new IOException("Connection timeout");
                tcp.ReceiveTimeout = 10000; tcp.SendTimeout = 10000;
                using (var ssl = new SslStream(tcp.GetStream(), false, delegate(object sender, System.Security.Cryptography.X509Certificates.X509Certificate cert, System.Security.Cryptography.X509Certificates.X509Chain chain, SslPolicyErrors errors) {
                    if (cert == null) return false;
                    using (var sha = SHA256.Create()) return Hex(sha.ComputeHash(cert.GetRawCertData())) == Pin;
                })) {
                    ssl.ReadTimeout = 10000; ssl.WriteTimeout = 10000;
                    ssl.AuthenticateAsClient(Host, null, SslProtocols.Tls12, false);
                    byte[] magic = Encoding.ASCII.GetBytes("ELS-FRIENDS/1\n"), body = Encoding.UTF8.GetBytes(json.Serialize(request));
                    if (body.Length > 2048) throw new IOException("Request too long");
                    ssl.Write(magic, 0, magic.Length); ssl.WriteByte((byte)(body.Length >> 8)); ssl.WriteByte((byte)body.Length); ssl.Write(body, 0, body.Length); ssl.Flush();
                    if (!Exact(ssl, magic.Length).SequenceEqual(magic)) throw new IOException("Unexpected server");
                    byte[] size = Exact(ssl, 2); int length = size[0]*256+size[1];
                    if (length < 1 || length > 2048) throw new IOException("Response too long");
                    return json.Deserialize<Dictionary<string, object>>(Encoding.UTF8.GetString(Exact(ssl, length)));
                }
            }
        }
        public static bool Ok(Dictionary<string,object> reply) { return reply.ContainsKey("ok") && Object.Equals(reply["ok"], true); }
        public static string Error(Dictionary<string,object> reply) {
            string code = reply.ContainsKey("error") ? Convert.ToString(reply["error"]) : "";
            switch (code) {
                case "name_taken": return "这个账号已经有人使用，请换一个账号。";
                case "invalid_name": return "账号需为 3–24 位小写字母、数字或下划线，并以字母开头。";
                case "invalid_password": return "密码需为 8–64 个字符，不能包含换行。";
                case "bad_credentials": return "账号或密码不正确，或登录已过期。";
                case "account_playing": return "请先正常退出此账号的游戏，再恢复起点。";
                case "recovery_stale": return "角色状态已变化，请刷新角色列表后重试。";
                case "recovery_conflict": return "操作资料已变化，请刷新角色列表后重试。";
                case "recovery_backup_failed": return "存档备份未能完成，角色位置未修改，请稍后重试。";
                case "recovery_unavailable": return "当前角色暂不可恢复，请刷新列表或稍后重试。";
                case "rate_limited": return "操作有些频繁，请稍后再试。";
                case "registration_closed": return "服务器暂未开放注册。";
                case "registration_full": return "朋友服账号名额已满，请联系房主。";
                default: return "服务器暂时无法完成操作，请稍后再试。";
            }
        }
        public static string LaunchFailure(string logPath) {
            try {
                const string marker="ELS_LAUNCH_ERROR: ";
                foreach(string line in File.ReadAllLines(logPath,Encoding.UTF8).Reverse())
                    if(line.StartsWith(marker,StringComparison.Ordinal))return line.Substring(marker.Length);
            }catch{}
            return "启动未能完成，请查看诊断日志或将日志发给房主。";
        }
        public static string Protect(string token) { return Convert.ToBase64String(ProtectedData.Protect(Encoding.UTF8.GetBytes(token), Entropy, DataProtectionScope.CurrentUser)); }
        public static string Unprotect(string token) { return Encoding.UTF8.GetString(ProtectedData.Unprotect(Convert.FromBase64String(token), Entropy, DataProtectionScope.CurrentUser)); }
        public static Dictionary<string,object> LoadSettings() {
            SettingsRecovered=false;
            string path=Path.Combine(DataRoot,"settings.json");
            if(!File.Exists(path))return new Dictionary<string,object>();
            try {
                string text=File.ReadAllText(path,Encoding.UTF8);
                if(String.IsNullOrWhiteSpace(text)){SettingsRecovered=true;return new Dictionary<string,object>();}
                var settings=Json.Deserialize<Dictionary<string,object>>(text);
                // JavaScriptSerializer returns null for both an empty document
                // and JSON null. A successful parse need not produce a map.
                if(settings==null){SettingsRecovered=true;return new Dictionary<string,object>();}
                foreach(string key in new[]{"client","name","login","saved_password"}) {
                    if(settings.ContainsKey(key)&&!(settings[key] is string)){settings.Remove(key);SettingsRecovered=true;}
                }
                if(settings.ContainsKey("remember")&&!(settings["remember"] is bool)){settings.Remove("remember");SettingsRecovered=true;}
                if(settings.ContainsKey("client")) {
                    string client=(string)settings["client"];
                    // Registration and legacy-account recovery may happen
                    // before directory selection. An empty path is unset.
                    if(String.IsNullOrWhiteSpace(client))settings.Remove("client");
                    else try{if(!Path.IsPathRooted(client))throw new ArgumentException();Path.GetFullPath(client);Path.GetDirectoryName(client);}catch(ArgumentException){settings.Remove("client");SettingsRecovered=true;}catch(NotSupportedException){settings.Remove("client");SettingsRecovered=true;}catch(PathTooLongException){settings.Remove("client");SettingsRecovered=true;}
                }
                if(settings.ContainsKey("name")&&!System.Text.RegularExpressions.Regex.IsMatch((string)settings["name"],"^$|^[a-z][a-z0-9_]{2,23}$")){settings.Remove("name");settings.Remove("login");settings.Remove("saved_password");SettingsRecovered=true;}
                return settings;
            } catch {SettingsRecovered=true;return new Dictionary<string,object>();}
        }
        static string StartupFailure(Exception error) {
            try {
                var chain=new List<object>();
                for(var current=error;current!=null;current=current.InnerException)chain.Add(new {type=current.GetType().FullName,hresult=current.HResult,stack=current.StackTrace});
                string file=Path.Combine(DataRoot,"logs","startup-error.json");
                // Record exception types and code locations, never form values
                // or exception messages that might contain a credential.
                PrivateWrite(file,Json.Serialize(new {at=DateTimeOffset.Now.ToString("o"),exceptions=chain}));return file;
            }catch{return null;}
        }
        public static void PrivateWrite(string path, string text) {
            string folder=Path.GetDirectoryName(path);Directory.CreateDirectory(folder);
            var user=WindowsIdentity.GetCurrent().User;
            var system=new SecurityIdentifier(WellKnownSidType.LocalSystemSid,null);
            var directorySecurity=new DirectorySecurity();directorySecurity.SetAccessRuleProtection(true,false);
            foreach(var sid in new[]{user,system})directorySecurity.AddAccessRule(new FileSystemAccessRule(sid,FileSystemRights.FullControl,InheritanceFlags.ContainerInherit|InheritanceFlags.ObjectInherit,PropagationFlags.None,AccessControlType.Allow));
            // Set security through a path-based handle opened with WRITE_DAC.
            // FileStream(FileAccess.Write) does not possess that access right.
            Directory.SetAccessControl(folder,directorySecurity);
            string temporary=Path.Combine(folder,".write-"+Guid.NewGuid().ToString("N"));
            try {
                File.WriteAllText(temporary,text,new UTF8Encoding(false));
                if(File.Exists(path))File.Replace(temporary,path,null);else File.Move(temporary,path);
                var fileSecurity=new FileSecurity();fileSecurity.SetAccessRuleProtection(true,false);
                foreach(var sid in new[]{user,system})fileSecurity.AddAccessRule(new FileSystemAccessRule(sid,FileSystemRights.FullControl,AccessControlType.Allow));
                File.SetAccessControl(path,fileSecurity);
            } finally {if(File.Exists(temporary))File.Delete(temporary);}
        }
        public static string EnsurePayload(Action<string> progress) {return ComponentRuntime.Ensure(progress);}
        public static int RunPython(string root, string arguments, string logPath) {
            var info = new ProcessStartInfo(Path.Combine(root,"python","python.exe"),"-X utf8 "+arguments);
            info.UseShellExecute=false; info.CreateNoWindow=true; info.WorkingDirectory=root; info.RedirectStandardOutput=true; info.RedirectStandardError=true;
            info.StandardOutputEncoding=Encoding.UTF8; info.StandardErrorEncoding=Encoding.UTF8;
            using (var log = new StreamWriter(logPath,false,Encoding.UTF8)) using (var process = new Process()) {
                process.StartInfo=info;
                DataReceivedEventHandler receive=delegate(object s,DataReceivedEventArgs e) { if(e.Data!=null) lock(log) {log.WriteLine(e.Data);log.Flush();} };
                process.OutputDataReceived+=receive; process.ErrorDataReceived+=receive;
                process.Start(); process.BeginOutputReadLine(); process.BeginErrorReadLine(); process.WaitForExit(); return process.ExitCode;
            }
        }
        [STAThread] static int Main(string[] args) {
            Application.EnableVisualStyles(); Application.SetCompatibleTextRenderingDefault(false);
            try {
                if (args.Length > 0 && args[0] == "--ui-test") {
                    using(var form=new MainForm(true)) form.Snapshot(args[1]);
                    using(var form=new RegisterForm("")) form.Snapshot(Path.ChangeExtension(args[1],"register.png"));
                    return 0;
                }
                if(args.Length>0&&args[0]=="--window-test") {
                    object main,registration;
                    using(var form=new MainForm(true))main=form.VerifyWindowForTest();
                    using(var form=new RegisterForm(""))registration=form.VerifyWindowForTest();
                    File.WriteAllText(args[1],Json.Serialize(new {ok=true,main=main,registration=registration}));return 0;
                }
                if(args.Length>0&&args[0]=="--startup-test") {
                    DataRoot=Path.GetFullPath(args[2]);
                    using(var form=new MainForm()) {
                        bool recovered=SettingsRecovered;
                        string image=Path.ChangeExtension(args[1],"png");form.Snapshot(image);
                        File.WriteAllText(args[1],Json.Serialize(new {ok=true,normal_form_initialized=true,settings_recovered=recovered,main_form_rendered=true}));
                    }
                    return 0;
                }
                if(args.Length>0 && args[0]=="--settings-test") {
                    DataRoot=Path.GetFullPath(args[2]);
                    string secret="proof-session-"+Guid.NewGuid().ToString("N"),client="D:\\艾尔之光\\data\\x2_dx11.exe";
                    using(var form=new MainForm(true)){if(!form.SaveClientForTest(client))throw new Exception("Directory save failed");}
                    var settings=LoadSettings();if(Convert.ToString(settings["client"])!=client)throw new Exception("Directory recovery failed");
                    settings["name"]="proof_friend";settings["login"]=Protect(secret);
                    string file=Path.Combine(DataRoot,"settings.json");PrivateWrite(file,Json.Serialize(settings));
                    var restored=LoadSettings();if(Unprotect(Convert.ToString(restored["login"]))!=secret)throw new Exception("Remembered login failed");
                    if(File.ReadAllText(file).Contains(secret))throw new Exception("Plaintext credential stored");
                    var rules=File.GetAccessControl(file).GetAccessRules(true,true,typeof(SecurityIdentifier));
                    foreach(FileSystemAccessRule rule in rules)if(rule.IdentityReference.Value!=WindowsIdentity.GetCurrent().User.Value&&rule.IdentityReference.Value!="S-1-5-18")throw new Exception("Unexpected settings ACL");
                    string session=Path.Combine(DataRoot,"sessions","proof.json");PrivateWrite(session,"{}");PrivateWrite(session,"{\"updated\":true}");File.Delete(session);
                    File.WriteAllText(args[1],Json.Serialize(new {ok=true,client_directory_saved=true,disk_roundtrip=true,remembered_login_dpapi=true,atomic_overwrite=true,private_acl=true,session_write_and_cleanup=true}));return 0;
                }
                if(args.Length>0 && args[0]=="--settings-restore-test") {
                    DataRoot=Path.GetFullPath(args[2]);
                    using(var form=new MainForm()) {
                        if(!form.RestoredSettingsForTest())throw new Exception("Fresh process did not restore settings");
                        form.ForgetLoginForTest();if(LoadSettings().ContainsKey("login"))throw new Exception("Uncheck did not forget login");
                    }
                    string normalRoot=DataRoot;DataRoot=Path.Combine(normalRoot,"blocked-as-file");File.WriteAllText(DataRoot,"{}");
                    using(var form=new MainForm(true)){if(form.SaveClientForTest("D:\\艾尔之光\\data\\x2_dx11.exe"))throw new Exception("Invalid destination accepted");}
                    File.Delete(DataRoot);DataRoot=normalRoot;
                    File.WriteAllText(args[1],Json.Serialize(new {ok=true,fresh_process_restored_directory=true,fresh_process_restored_login=true,uncheck_forgets_login=true,save_failure_handled=true}));return 0;
                }
                if(args.Length>0 && args[0]=="--account-test") {
                    string name="launchtest_"+Guid.NewGuid().ToString("N").Substring(0,10), password=Guid.NewGuid().ToString("N")+"Ab8!";
                    var registered=Api(new Dictionary<string,object>{{"op","register"},{"name",name},{"password",password}});
                    if(!Ok(registered))throw new Exception("Registration failed");
                    var wrong=Api(new Dictionary<string,object>{{"op","login"},{"name",name},{"password","wrong-pass"}});if(Ok(wrong))throw new Exception("Wrong password accepted");
                    var logged=Api(new Dictionary<string,object>{{"op","login"},{"name",name},{"password",password}});if(!Ok(logged))throw new Exception("Login failed");
                    var resumed=Api(new Dictionary<string,object>{{"op","resume"},{"name",name},{"token",logged["token"]}});if(!Ok(resumed))throw new Exception("Resume failed");
                    File.WriteAllText(args[1],Json.Serialize(new {ok=true,name=name,account_id=registered["account_id"],registration=true,login=true,remembered_session=true,wrong_password_rejected=true}));return 0;
                }
                if (args.Length > 0 && args[0] == "--self-test") {
                    DataRoot=Path.GetFullPath(args[2]); string root=EnsurePayload(delegate(string value){});
                    Directory.CreateDirectory(Path.Combine(DataRoot,"logs"));
                    if (Unprotect(Protect("test-roundtrip")) != "test-roundtrip") throw new Exception("DPAPI failed");
                    int code=RunPython(root,"-c "+Quote("import frida, psutil; from els_server.friends_bridge import Bridge; print('runtime_ok')"),Path.Combine(DataRoot,"logs","self-test.log"));
                    if(code!=0) throw new Exception("Embedded runtime failed");
                    var status=Api(new Dictionary<string,object>{{"op","status"}}); if(!Ok(status)) throw new Exception("Account API unavailable");
                    File.WriteAllText(args[1],Json.Serialize(new {ok=true,runtime=root,registration_enabled=status["registration_enabled"],dpapi=true,payload_sha256=PayloadHash}));return 0;
                }
                if(args.Length>0&&args[0]=="--update-test") {DataRoot=Path.GetFullPath(args[2]);File.WriteAllText(args[1],Json.Serialize(AutoUpdate.Test(args[3])));return 0;}
                if(args.Length>0&&args[0]=="--update-network-test") {DataRoot=Path.GetFullPath(args[2]);var release=AutoUpdate.Latest();File.WriteAllText(args[1],Json.Serialize(new {ok=true,version=release.Version,sha256=release.Hash,size=release.Size,tls_pinned=true,signature_verified=true}));return 0;}
                if(args.Length>0&&args[0]=="--update-download-test") {DataRoot=Path.GetFullPath(args[2]);var release=AutoUpdate.Verify(File.ReadAllText(args[3]));string path=AutoUpdate.Download(release,delegate{});File.WriteAllText(args[1],Json.Serialize(new {ok=true,path=path,sha256=release.Hash,verified=AutoUpdate.ValidFile(path,release)}));return 0;}
                if(args.Length>0&&args[0]=="--password-save-test") {
                    DataRoot=Path.GetFullPath(args[2]);string password="Fixture-Only-"+Guid.NewGuid().ToString("N"),name="proof_password";
                    using(var form=new MainForm(true)){if(!form.SavePasswordForTest(name,password))throw new Exception("Password save failed");}
                    var settings=LoadSettings();if(Unprotect(Convert.ToString(settings["saved_password"]))!=password)throw new Exception("DPAPI password roundtrip failed");
                    if(File.ReadAllText(Path.Combine(DataRoot,"settings.json")).Contains(password))throw new Exception("Plaintext password written");
                    using(var form=new MainForm()){if(!form.PasswordRestoredForTest(name,password))throw new Exception("Automatic fill failed");if(!form.PasswordAfterClearedForTest(password))throw new Exception("Saved password unavailable after login box cleared");if(!form.ChangeAccountClearsPasswordForTest())throw new Exception("Password carried to another account");}
                    if(LoadSettings().ContainsKey("saved_password"))throw new Exception("Another account retained old password");
                    using(var form=new MainForm()){if(!form.SavePasswordForTest(name,password))throw new Exception("Password resave failed");form.ForgetLoginForTest();}
                    if(LoadSettings().ContainsKey("saved_password")||LoadSettings().ContainsKey("login"))throw new Exception("Uncheck retained saved credentials");
                    File.WriteAllText(args[1],Json.Serialize(new {ok=true,current_user_DPAPI=true,plaintext_not_on_disk=true,automatic_password_fill=true,saved_password_reusable_after_login_box_cleared=true,account_switch_clears_password=true,uncheck_removes_saved_password_and_token=true,game_or_network_access=false}));return 0;
                }
                if(args.Length>0&&args[0]=="--components-test") {DataRoot=Path.GetFullPath(args[2]);string root=EnsurePayload(delegate(string value){});File.WriteAllText(args[1],Json.Serialize(new {ok=true,root=root,stats=ComponentRuntime.LastResult}));return 0;}
                AutoUpdate.WaitParent(args);
                if((args.Length==0||args[0]=="--updated-parent")&&AutoUpdate.StartCached())return 0;
                if(args.Length>0&&args[0]=="--design-test") {DataRoot=Path.GetFullPath(args[2]);File.WriteAllText(args[1],Json.Serialize(DesignProof.Run(args[3])));return 0;}
                string launchSmoke=null;
                if(args.Length>0&&args[0]=="--launch-smoke") {launchSmoke=Path.GetFullPath(args[1]);DataRoot=Path.GetFullPath(args[2]);}
                bool first; using(var mutex=new Mutex(true,"Local\\ElsFriendsLauncher-"+WindowsIdentity.GetCurrent().User.Value,out first)) {
                    if(!first) {AutoUpdate.CancelOwnActivation();if(launchSmoke!=null)return 2;MessageBox.Show("启动器已经打开，请在任务栏中切换。","朋友服");return 0;}
                    using(var form=new MainForm()) {
                        if(launchSmoke==null)AutoUpdate.ConfirmHealthy();
                        bool smokePassed=false;
                        using(var watchdog=new System.Windows.Forms.Timer {Interval=20000}) {
                            if(launchSmoke!=null) {
                                form.PrepareLaunchSmoke();
                                form.StartupReady+=delegate {
                                    try {
                                        if(!form.ServerOnlineForTest||!form.NativeFramelessForTest)throw new Exception("Normal launch readiness failed");
                                        File.WriteAllText(launchSmoke,Json.Serialize(new {ok=true,production_startup_branch=true,single_instance_mutex=true,normal_form_initialized=true,message_loop_ran=true,shown_event_completed=true,server_online=true,native_frameless=true,remembered_login_restored=form.RememberedLoginForTest}));smokePassed=true;
                                    }catch{smokePassed=false;}finally{form.Close();}
                                };
                                watchdog.Tick+=delegate{form.Close();};watchdog.Start();
                            }
                            Application.Run(form);
                            if(launchSmoke!=null&&!smokePassed)return 1;
                        }
                    }
                }
                if(AutoUpdate.PendingLauncher!=null)AutoUpdate.Start(AutoUpdate.PendingLauncher);
                return 0;
            } catch(Exception error) {string log=StartupFailure(error);if(args.Length>0)return 1;MessageBox.Show("启动器暂时无法打开，请联系房主协助处理。"+(log==null?"":"\n诊断日志："+log),"朋友服",MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;}
        }
    }

    static class Theme {
        public static Color Ink=Color.FromArgb(34,49,72),Muted=Color.FromArgb(126,142,162),Canvas=Color.FromArgb(244,247,251),Cyan=Color.FromArgb(20,155,190),Coral=Color.FromArgb(248,93,117);
        public static GraphicsPath Round(RectangleF r,float radius) {
            float d=radius*2;var path=new GraphicsPath();
            path.AddArc(r.X,r.Y,d,d,180,90);path.AddArc(r.Right-d,r.Y,d,d,270,90);path.AddArc(r.Right-d,r.Bottom-d,d,d,0,90);path.AddArc(r.X,r.Bottom-d,d,d,90,90);path.CloseFigure();return path;
        }
    }
    class SoftPanel:Panel {
        public SoftPanel(){DoubleBuffered=true;BackColor=Color.White;}
        protected override void OnPaintBackground(PaintEventArgs e) {
            e.Graphics.Clear(Parent==null?Theme.Canvas:Parent.BackColor);e.Graphics.SmoothingMode=SmoothingMode.AntiAlias;
            using(var path=Theme.Round(new RectangleF(0,0,Width-1,Height-1),16))using(var b=new SolidBrush(BackColor))using(var p=new Pen(Color.FromArgb(220,233,239))){e.Graphics.FillPath(b,path);e.Graphics.DrawPath(p,path);}
        }
    }
    class ScenePanel:Panel {
        Image art;
        public ScenePanel(){DoubleBuffered=true;using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("ElsFriends.Ruben"))using(var source=Image.FromStream(stream))art=new Bitmap(source);}
        protected override void Dispose(bool disposing){if(disposing&&art!=null)art.Dispose();base.Dispose(disposing);}
        protected override void OnPaintBackground(PaintEventArgs e){
            e.Graphics.Clear(Theme.Canvas);e.Graphics.SmoothingMode=SmoothingMode.AntiAlias;
            using(var path=Theme.Round(new RectangleF(0,0,Width-1,Height-1),20)){
                var state=e.Graphics.Save();e.Graphics.SetClip(path);
                float scale=Math.Max((float)Width/art.Width,(float)Height/art.Height);float w=art.Width*scale,h=art.Height*scale;
                e.Graphics.DrawImage(art,new RectangleF((Width-w)*.56f,(Height-h)*.55f,w,h));
                using(var shade=new LinearGradientBrush(ClientRectangle,Color.FromArgb(231,9,41,53),Color.FromArgb(8,9,41,53),0f))e.Graphics.FillRectangle(shade,ClientRectangle);
                using(var f=new Font("Segoe UI",8,FontStyle.Bold))using(var b=new SolidBrush(Color.FromArgb(148,221,232)))e.Graphics.DrawString("—  THE JOURNEY CONTINUES",f,b,27,21);
                using(var f=new Font("Microsoft YaHei UI",25,FontStyle.Bold))e.Graphics.DrawString("再一次，和朋友一起冒险。",f,Brushes.White,new RectangleF(25,57,Width-50,58));
                using(var f=new Font("Microsoft YaHei UI",9))e.Graphics.DrawString("从熟悉的魔奇出发，在艾里奥斯相遇。\n各自的角色与进度，都会为你保留。",f,Brushes.White,new RectangleF(28,122,Width-56,49));
                using(var f=new Font("Microsoft YaHei UI",7))e.Graphics.DrawString("原生场景 · 魔奇 RUBEN",f,Brushes.White,Width-155,Height-28);
                e.Graphics.Restore(state);
            }
        }
    }
    class BrandPanel:Panel {
        public BrandPanel(){DoubleBuffered=true;BackColor=Color.FromArgb(248,252,254);}
        protected override void OnPaint(PaintEventArgs e) {
            e.Graphics.SmoothingMode=SmoothingMode.AntiAlias;
            using(var p=new Pen(Color.FromArgb(225,235,240)))e.Graphics.DrawLine(p,Width-1,0,Width-1,Height);
            using(var b=new SolidBrush(Color.FromArgb(226,247,252)))e.Graphics.FillEllipse(b,20,29,39,43);
            PointF top=new PointF(39,32),left=new PointF(27,46),right=new PointF(51,46),bottom=new PointF(39,65),mid=new PointF(39,49);
            using(var b=new SolidBrush(Color.FromArgb(89,220,247)))e.Graphics.FillPolygon(b,new[]{top,left,mid});
            using(var b=new SolidBrush(Theme.Cyan))e.Graphics.FillPolygon(b,new[]{top,right,mid});
            using(var b=new SolidBrush(Color.FromArgb(0,112,157)))e.Graphics.FillPolygon(b,new[]{left,bottom,mid});
            using(var b=new SolidBrush(Color.FromArgb(8,175,213)))e.Graphics.FillPolygon(b,new[]{right,bottom,mid});
            using(var b=new SolidBrush(Theme.Ink))using(var f=new Font("Microsoft YaHei UI",17,FontStyle.Bold|FontStyle.Italic))e.Graphics.DrawString("艾尔之光",f,b,63,29);
            using(var b=new SolidBrush(Theme.Muted))using(var f=new Font("Segoe UI",7))e.Graphics.DrawString("ELRIOS  FRIENDS",f,b,65,62);
            using(var b=new SolidBrush(Theme.Muted))using(var f=new Font("Microsoft YaHei UI",8))e.Graphics.DrawString("冒险空间",f,b,28,118);
            using(var path=Theme.Round(new RectangleF(17,148,Width-34,43),12))using(var b=new SolidBrush(Color.FromArgb(226,244,251)))e.Graphics.FillPath(b,path);
            using(var b=new SolidBrush(Theme.Cyan))using(var f=new Font("Microsoft YaHei UI",10,FontStyle.Bold))e.Graphics.DrawString("◇   朋友联机",f,b,30,159);
            using(var b=new SolidBrush(Theme.Cyan))e.Graphics.FillEllipse(b,Width-37,166,5,5);
            using(var b=new SolidBrush(Theme.Muted))using(var f=new Font("Microsoft YaHei UI",8.5f))e.Graphics.DrawString("与好友一起继续旅程",f,b,29,210);
            using(var path=Theme.Round(new RectangleF(17,Height-125,Width-34,61),12))using(var b=new SolidBrush(Color.FromArgb(238,246,249)))e.Graphics.FillPath(b,path);
            using(var b=new SolidBrush(Color.FromArgb(41,182,142)))e.Graphics.FillEllipse(b,28,Height-106,6,6);
            using(var b=new SolidBrush(Theme.Ink))using(var f=new Font("Microsoft YaHei UI",8))e.Graphics.DrawString("你的朋友世界",f,b,41,Height-112);
            using(var b=new SolidBrush(Theme.Muted))using(var f=new Font("Microsoft YaHei UI",7))e.Graphics.DrawString("进度保存在服务器",f,b,41,Height-91);
            using(var b=new SolidBrush(Theme.Muted))using(var f=new Font("Segoe UI",7))e.Graphics.DrawString("FRIENDS EDITION     02",f,b,26,Height-38);
        }
    }
    class ProofForm:Form {
        protected bool proofMode=false;
        bool smokeWindow=false;
        protected virtual bool WindowResizable {get{return true;}}
        readonly Dictionary<string,WindowButton> windowButtons=new Dictionary<string,WindowButton>();
        Control windowHeader;
        [StructLayout(LayoutKind.Sequential)] struct NativePoint {public int X,Y;}
        [StructLayout(LayoutKind.Sequential)] struct NativeRect {public int Left,Top,Right,Bottom;}
        [StructLayout(LayoutKind.Sequential)] struct MinMaxInfo {public NativePoint Reserved,MaxSize,MaxPosition,MinTrack,MaxTrack;}
        [DllImport("user32.dll")] static extern bool ReleaseCapture();
        [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr hwnd,int message,IntPtr wparam,IntPtr lparam);
        [DllImport("user32.dll",EntryPoint="GetWindowLongPtrW")] static extern IntPtr GetWindowLongPtr(IntPtr hwnd,int index);
        [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hwnd,out NativeRect rect);
        [DllImport("user32.dll")] static extern bool GetClientRect(IntPtr hwnd,out NativeRect rect);
        [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr hwnd);
        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd,int attribute,ref int value,int size);
        int ResizeMargin {get{return Math.Max(5,(int)Math.Round(6*DeviceDpi/96.0));}}
        public ProofForm(){FormBorderStyle=FormBorderStyle.None;Padding=new Padding(6);}
        protected override bool ShowWithoutActivation {get{return proofMode||smokeWindow;}}
        protected override CreateParams CreateParams {get{var p=base.CreateParams;p.Style&=~0x00c00000;p.Style|=0x00080000;if(WindowResizable)p.Style|=0x00040000|0x00020000|0x00010000;if(proofMode||smokeWindow)p.ExStyle|=0x08000080;return p;}}
        public void PrepareLaunchSmoke(){smokeWindow=true;ShowInTaskbar=false;StartPosition=FormStartPosition.Manual;Location=new Point(-20000,-20000);}
        public bool NativeFramelessForTest {get{NativeRect outer,client;GetWindowRect(Handle,out outer);GetClientRect(Handle,out client);return FormBorderStyle==FormBorderStyle.None&&(GetWindowLongPtr(Handle,-16).ToInt64()&0x00c00000)==0&&outer.Right-outer.Left==client.Right&&outer.Bottom-outer.Top==client.Bottom;}}
        protected override void OnHandleCreated(EventArgs e){base.OnHandleCreated(e);try{int rounded=2;DwmSetWindowAttribute(Handle,33,ref rounded,4);}catch(DllNotFoundException){}catch(EntryPointNotFoundException){}}
        protected override void OnResize(EventArgs e){base.OnResize(e);Padding=new Padding(WindowState==FormWindowState.Maximized?0:(WindowResizable?ResizeMargin:1));foreach(var button in windowButtons.Values)button.Invalidate();}
        protected override void WndProc(ref Message m){
            if(m.Msg==0x83){m.Result=IntPtr.Zero;return;} // No Windows caption or non-client frame.
            if(m.Msg==0x86){m.Result=new IntPtr(1);return;}
            if(m.Msg==0x24&&WindowResizable){
                base.WndProc(ref m);
                var screen=Screen.FromHandle(m.HWnd);var work=screen.WorkingArea;var bounds=screen.Bounds;
                var info=(MinMaxInfo)Marshal.PtrToStructure(m.LParam,typeof(MinMaxInfo));
                info.MaxPosition.X=work.Left-bounds.Left;info.MaxPosition.Y=work.Top-bounds.Top;info.MaxSize.X=work.Width;info.MaxSize.Y=work.Height;
                info.MinTrack.X=MinimumSize.Width;info.MinTrack.Y=MinimumSize.Height;
                Marshal.StructureToPtr(info,m.LParam,false);return;
            }
            if(m.Msg==0x84&&WindowResizable&&WindowState==FormWindowState.Normal){
                long packed=m.LParam.ToInt64();var point=PointToClient(new Point((short)(packed&65535),(short)((packed>>16)&65535)));
                bool left=point.X<ResizeMargin,right=point.X>=ClientSize.Width-ResizeMargin,top=point.Y<ResizeMargin,bottom=point.Y>=ClientSize.Height-ResizeMargin;
                int hit=top&&left?13:top&&right?14:bottom&&left?16:bottom&&right?17:left?10:right?11:top?12:bottom?15:0;
                if(hit!=0){m.Result=new IntPtr(hit);return;}
            }
            base.WndProc(ref m);
        }
        protected void BindWindowDrag(Control control){if(windowHeader==null)windowHeader=control;control.MouseDown+=delegate(object sender,MouseEventArgs e){if(e.Button!=MouseButtons.Left||proofMode)return;if(e.Clicks==2&&WindowResizable){ToggleWindowSize();return;}ReleaseCapture();SendMessage(Handle,0xa1,new IntPtr(2),IntPtr.Zero);};}
        void ToggleWindowSize(){if(WindowResizable)WindowState=WindowState==FormWindowState.Maximized?FormWindowState.Normal:FormWindowState.Maximized;}
        protected Control WindowControls(bool full){
            var strip=new FlowLayoutPanel {Dock=DockStyle.Fill,FlowDirection=FlowDirection.LeftToRight,WrapContents=false,Margin=Padding.Empty,Padding=Padding.Empty,BackColor=Color.Transparent};
            foreach(string action in full?new[]{"minimize","maximize","close"}:new[]{"close"}){
                var button=new WindowButton(action){Size=new Size(31,30),Margin=new Padding(2,0,2,0)};
                if(action=="minimize")button.Click+=delegate{WindowState=FormWindowState.Minimized;};
                else if(action=="maximize")button.Click+=delegate{ToggleWindowSize();};
                else button.Click+=delegate{Close();};
                strip.Controls.Add(button);windowButtons.Add(action,button);
                if(!full)CancelButton=button;
            }
            return strip;
        }
        public object VerifyWindowForTest(){
            PerformLayout();foreach(Control control in Controls)control.PerformLayout();
            IntPtr hwnd=Handle;NativeRect outer,client;GetWindowRect(hwnd,out outer);GetClientRect(hwnd,out client);
            if(FormBorderStyle!=FormBorderStyle.None||(GetWindowLongPtr(hwnd,-16).ToInt64()&0x00c00000)!=0)throw new Exception("Native caption still present");
            if(outer.Right-outer.Left!=client.Right||outer.Bottom-outer.Top!=client.Bottom)throw new Exception("Non-client border still present");
            if(windowHeader==null)throw new Exception("No draggable title area");
            foreach(Control sibling in windowHeader.Parent.Controls)if(sibling!=windowHeader&&sibling.Bounds.IntersectsWith(windowHeader.Bounds))throw new Exception("Titlebar overlaps window content");
            foreach(var button in windowButtons.Values)for(Control child=button;child.Parent!=null;child=child.Parent)if(!child.Parent.ClientRectangle.Contains(child.Bounds))throw new Exception("Window button is clipped");
            int targets=0;
            if(WindowResizable){
                int[,] points={{1,1,13},{ClientSize.Width-2,1,14},{1,ClientSize.Height-2,16},{ClientSize.Width-2,ClientSize.Height-2,17},{1,ClientSize.Height/2,10},{ClientSize.Width-2,ClientSize.Height/2,11},{ClientSize.Width/2,1,12},{ClientSize.Width/2,ClientSize.Height-2,15}};
                for(int i=0;i<8;i++){var p=PointToScreen(new Point(points[i,0],points[i,1]));long packed=((long)(p.Y&65535)<<16)|(uint)(p.X&65535);if(SendMessage(hwnd,0x84,IntPtr.Zero,new IntPtr(packed)).ToInt32()!=points[i,2])throw new Exception("Resize target mismatch");targets++;}
                IntPtr memory=Marshal.AllocHGlobal(Marshal.SizeOf(typeof(MinMaxInfo)));
                try{Marshal.StructureToPtr(new MinMaxInfo(),memory,false);SendMessage(hwnd,0x24,IntPtr.Zero,memory);var info=(MinMaxInfo)Marshal.PtrToStructure(memory,typeof(MinMaxInfo));var work=Screen.FromHandle(hwnd).WorkingArea;if(info.MaxSize.X!=work.Width||info.MaxSize.Y!=work.Height)throw new Exception("Maximize covers taskbar");}finally{Marshal.FreeHGlobal(memory);}
                windowButtons["minimize"].ClickForTest();if(WindowState!=FormWindowState.Minimized)throw new Exception("Minimize button failed");WindowState=FormWindowState.Normal;
                windowButtons["maximize"].ClickForTest();if(WindowState!=FormWindowState.Maximized)throw new Exception("Maximize button failed");windowButtons["maximize"].ClickForTest();if(WindowState!=FormWindowState.Normal)throw new Exception("Restore button failed");
            }
            if(IsWindowVisible(hwnd))throw new Exception("Hidden window test became visible");
            windowButtons["close"].ClickForTest();if(!IsDisposed)throw new Exception("Close button failed");
            return new {frameless=true,client_fills_window=true,resize_targets=targets,minimize_maximize_restore=WindowResizable,work_area_maximize=WindowResizable,custom_close=true,titlebar_unobstructed=true,window_controls_unclipped=true};
        }
        public void Snapshot(string path) {
            proofMode=true;ShowInTaskbar=false;StartPosition=FormStartPosition.Manual;Location=new Point(-20000,-20000);
            Show();Application.DoEvents();PerformLayout();Update();
            using(var bitmap=new Bitmap(Width,Height)){DrawToBitmap(bitmap,new Rectangle(0,0,Width,Height));bitmap.Save(path);}Hide();
        }
    }
    partial class MainForm:ProofForm {
        public event EventHandler StartupReady;
        public bool ServerOnlineForTest {get{return server.Text.StartsWith("服务器在线");}}
        public bool RememberedLoginForTest {get{return !String.IsNullOrEmpty(token)&&tokenName==nameBox.Text;}}
        TextBox pathBox=new TextBox(),nameBox=new TextBox(),passwordBox=new TextBox();
        Button update=new SoftButton(),browse=new SoftButton(),login=new SoftButton(),register=new SoftButton(),diagnostics=new SoftButton(),recover=new SoftButton();
        CheckBox remember=new MotionCheckBox(); Label feedback=new Label(),server=new Label();
        string clientPath="",token=null,tokenName=null,rememberedPassword=null,passwordName=null; bool busy=false,openingDiagnostics=false,checkingUpdate=false;string readyUpdate=null;
        Color Ink=Theme.Ink,Blue=Theme.Cyan;
        public MainForm(bool test=false) {
            proofMode=test;
            Text="艾尔之光 · 朋友服"; ClientSize=new Size(1180,744); MinimumSize=new Size(1060,700); StartPosition=FormStartPosition.CenterScreen;
            Font=new Font("Microsoft YaHei UI",9); ForeColor=Ink;BackColor=Theme.Canvas; AutoScaleMode=AutoScaleMode.Dpi;
            try {Icon=Icon.ExtractAssociatedIcon(Assembly.GetExecutingAssembly().Location);}catch{}
            BuildDesign();
            AcceptButton=login;LoadSaved();
            remember.CheckedChanged+=delegate {if(!proofMode)Save();};
            nameBox.TextChanged+=delegate {if(nameBox.Text.Trim()!=tokenName)token=null;if(passwordName!=null&&nameBox.Text.Trim()!=passwordName){rememberedPassword=null;passwordName=null;passwordBox.Clear();}};
            FormClosing+=delegate(object sender,FormClosingEventArgs e) {if(busy) {e.Cancel=true;WindowState=FormWindowState.Minimized;}};
            Shown+=async delegate {if(!proofMode)await CheckUpdate(false);};
            Shown+=async delegate {if(proofMode)return;try {var result=await Task.Run(()=>Program.Api(new Dictionary<string,object>{{"op","status"}}));server.Text=Program.Ok(result)?"服务器在线 · 朋友测试服":"服务器准备中，请稍后重试";}catch {server.Text="暂时未连接到服务器，仍可选择客户端";}finally{if(StartupReady!=null)StartupReady(this,EventArgs.Empty);}};
        }
        void OpenExternal(string url) {try{AutoUpdate.OpenLink(url);}catch{Status("浏览器暂时无法打开，请复制地址后访问。",true);}}
        async Task CheckUpdate(bool manual) {
            if(checkingUpdate)return;checkingUpdate=true;update.Enabled=false;MotionEffects.Busy(update,true);update.Text="正在检查更新…";
            try {
                var release=await Task.Run(()=>AutoUpdate.Latest());
                if(release.Version<=AutoUpdate.Version){update.Text="V"+AutoUpdate.Version+" · 已是最新";if(manual){Status("当前启动器已是最新版本。");MotionEffects.Feedback(update,true);}return;}
                if(AutoUpdate.IsBlocked(release)){if(manual)AutoUpdate.PermitRetry();else{update.Text="V"+AutoUpdate.Version+" · 更新可重试";return;}}
                readyUpdate=await Task.Run(()=>AutoUpdate.Download(release,percent=>{if(!IsDisposed&&IsHandleCreated)BeginInvoke((Action)(()=>{update.Text="下载更新 "+percent+"%";MotionEffects.Progress(update,percent);}));}));
                update.Text="V"+release.Version+" · 更新并重启";MotionEffects.Feedback(update,true);Status("启动器更新已下载；可点击更新，或下次打开时自动使用新版。");
            }catch{if(!IsDisposed){update.Text="V"+AutoUpdate.Version+" · 重试更新";if(manual){Status("暂时无法检查或下载更新，当前版本仍可继续使用。",true);MotionEffects.Feedback(update,false);}}}
            finally{checkingUpdate=false;if(!IsDisposed){MotionEffects.Busy(update,false);MotionEffects.Progress(update,-1);update.Enabled=true;}}
        }
        void AddLabel(TableLayoutPanel layout,string text,int row) {layout.Controls.Add(new Label {Text=text,Dock=DockStyle.Fill,ForeColor=Ink},0,row);}
        void SetBusy(bool value) {busy=value;browse.Enabled=login.Enabled=register.Enabled=recover.Enabled=nameBox.Enabled=passwordBox.Enabled=remember.Enabled=!value;MotionEffects.Busy(activeOperation??login,value);if(!value){activeOperation=null;}UseWaitCursor=value;}
        void Status(string text,bool error=false) {feedback.Text=text;feedback.ForeColor=error?Color.FromArgb(190,65,86):Theme.Muted;if(error)MotionEffects.Feedback(activeOperation??login,false);}
        void Progress(string text) {if(!IsDisposed)BeginInvoke((Action)(()=>Status(text)));}
        void LoadSaved() {
            if(proofMode)return;
            var s=Program.LoadSettings();
            if(Program.SettingsRecovered)Status("上次设置未保存完整，请重新选择客户端目录并登录。");
            if(s.ContainsKey("client")&&!String.IsNullOrWhiteSpace(Convert.ToString(s["client"]))) {clientPath=Convert.ToString(s["client"]);pathBox.Text=Path.GetDirectoryName(clientPath);}
            if(s.ContainsKey("name"))nameBox.Text=Convert.ToString(s["name"]);
            if(s.ContainsKey("remember"))remember.Checked=Object.Equals(s["remember"],true);
            if(s.ContainsKey("login")) {try {token=Program.Unprotect(Convert.ToString(s["login"]));tokenName=nameBox.Text;Status("已记住登录，选择客户端后即可启动。");}catch{token=null;}}
            if(remember.Checked&&s.ContainsKey("saved_password")&&nameBox.Text.Length>0) {
                try {rememberedPassword=Program.Unprotect(Convert.ToString(s["saved_password"]));passwordName=nameBox.Text;passwordBox.Text=rememberedPassword;Status("已自动填入保存的密码，可直接登录。");}
                catch {rememberedPassword=null;passwordName=null;Status("保存的密码无法解密，请重新输入。");}
            }
            // Existing owners can keep their old server characters. Only
            // adjacent legacy settings are considered; no secret ships in EXE.
            if(token==null&&nameBox.Text.Length==0) {
                string home=Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
                foreach(string directory in new[]{home,Path.GetDirectoryName(home)}) {
                    try {
                        string file=Path.Combine(directory,"state","friends-client.json");if(!File.Exists(file))continue;
                        var old=Program.Json.Deserialize<Dictionary<string,object>>(File.ReadAllText(file,Encoding.UTF8));
                        if(Convert.ToString(old["host"])!=Program.Host||Convert.ToString(old["certificate_sha256"])!=Program.Pin)continue;
                        nameBox.Text=Convert.ToString(old["name"]);tokenName=nameBox.Text;token=Convert.ToString(old["token"]);Save();Status("已恢复旧账号，选择客户端后可直接启动。");break;
                    }catch{}
                }
            }
        }
        void RememberPassword(string name,string password) {
            if(!remember.Checked||String.IsNullOrEmpty(password))return;
            rememberedPassword=password;passwordName=name;
        }
        bool CommitAuthenticated(Dictionary<string,object> result,string name,string password) {
            name=name.Trim();
            if(!Program.Ok(result)||!System.Text.RegularExpressions.Regex.IsMatch(name,"^[a-z][a-z0-9_]{2,23}$"))throw new IOException("Invalid authenticated account");
            if(result.ContainsKey("name")&&Convert.ToString(result["name"])!=name)throw new IOException("Authenticated account differs");
            nameBox.Text=name;
            if(result.ContainsKey("token"))token=Convert.ToString(result["token"]);
            tokenName=name;RememberPassword(name,password);passwordBox.Clear();return Save();
        }
        string PasswordForAuth() {
            if(passwordBox.Text.Length>0)return passwordBox.Text;
            return remember.Checked&&passwordName==nameBox.Text.Trim()&&!String.IsNullOrEmpty(rememberedPassword)?rememberedPassword:"";
        }
        bool Save() {try {
            if(!remember.Checked) {if(passwordName==nameBox.Text.Trim()&&passwordBox.Text==rememberedPassword)passwordBox.Clear();rememberedPassword=null;passwordName=null;}
            var s=new Dictionary<string,object>{{"client",clientPath},{"name",nameBox.Text.Trim()},{"remember",remember.Checked}};
            if(remember.Checked&&token!=null&&tokenName==nameBox.Text.Trim())s["login"]=Program.Protect(token);
            if(remember.Checked&&passwordName==nameBox.Text.Trim()&&!String.IsNullOrEmpty(rememberedPassword))s["saved_password"]=Program.Protect(rememberedPassword);
            Program.PrivateWrite(Path.Combine(Program.DataRoot,"settings.json"),Program.Json.Serialize(s));return true;
        }catch(UnauthorizedAccessException){Status("无法保存启动器设置，请检查当前用户的数据目录权限。",true);return false;}catch(IOException){Status("设置文件暂时无法写入，请稍后重试。",true);return false;}}
        public bool SavePasswordForTest(string name,string password){nameBox.Text=name;passwordBox.Text=password;remember.Checked=true;RememberPassword(name.Trim(),password);return Save();}
        public bool PasswordRestoredForTest(string name,string password){return nameBox.Text==name&&passwordBox.Text==password&&rememberedPassword==password&&passwordName==name;}
        public bool PasswordAfterClearedForTest(string password){passwordBox.Clear();return PasswordForAuth()==password;}
        public bool ChangeAccountClearsPasswordForTest(){nameBox.Text="other_fixture";return passwordBox.Text.Length==0&&rememberedPassword==null&&passwordName==null&&Save();}

        public bool SaveClientForTest(string path){clientPath=path;pathBox.Text=Path.GetDirectoryName(path);return Save();}
        public bool RestoredSettingsForTest(){return clientPath=="D:\\艾尔之光\\data\\x2_dx11.exe"&&nameBox.Text=="proof_friend"&&tokenName=="proof_friend"&&token!=null&&token.StartsWith("proof-session-")&&passwordBox.Text.Length==0;}
        public void ForgetLoginForTest(){remember.Checked=false;}
        void ChooseClient(object sender,EventArgs e) {
            using(var dialog=new FolderBrowserDialog {Description="请选择客户端目录，或客户端的 data 文件夹",ShowNewFolderButton=false}) {
                if(Directory.Exists(pathBox.Text))dialog.SelectedPath=pathBox.Text;
                if(dialog.ShowDialog(this)!=DialogResult.OK)return;
                string p=Path.Combine(dialog.SelectedPath,"x2_dx11.exe");if(!File.Exists(p))p=Path.Combine(dialog.SelectedPath,"data","x2_dx11.exe");
                if(!File.Exists(p)) {Status("这个目录中没有找到 x2_dx11.exe，请选择完整客户端的目录。",true);return;}
                if(SaveClientForTest(p)){Status("客户端目录已保存。");MotionEffects.Feedback(browse,true);}
            }
        }
        async void Register(object sender,EventArgs e) {
            using(var dialog=new RegisterForm(nameBox.Text)) {
                if(dialog.ShowDialog(this)!=DialogResult.OK)return;
                activeOperation=register;SetBusy(true);Status("正在注册账号…");
                try {var request=new Dictionary<string,object>{{"op","register"},{"name",dialog.Account},{"password",dialog.Password}};var result=await Task.Run(()=>Program.Api(request));
                    if(!Program.Ok(result)){Status(Program.Error(result),true);return;}
                    CommitAuthenticated(result,dialog.Account,dialog.Password);MotionEffects.Feedback(register,true);Status("注册成功，点击“登录并启动游戏”即可进入。");
                }catch {Status("注册未能完成，请检查网络后重试；若提示账号已存在，可直接登录。",true);}finally{SetBusy(false);}
            }
        }
        async Task RecoverTutorial(){
            if(busy)return;string name=nameBox.Text.Trim(),password=PasswordForAuth();
            if(name.Length==0||(token==null&&password.Length==0)){Status("请输入账号和密码。",true);return;}
            SetBusy(true);Status("正在验证账号…");
            try{
                var request=token!=null&&tokenName==name&&password.Length==0?new Dictionary<string,object>{{"op","resume"},{"name",name},{"token",token}}:new Dictionary<string,object>{{"op","login"},{"name",name},{"password",password}};
                var result=await Task.Run(()=>Program.Api(request));if(!Program.Ok(result)){token=null;Save();Status(Program.Error(result),true);return;}
                CommitAuthenticated(result,name,password);
                using(var dialog=new TutorialRecoveryForm(name,token)){dialog.ShowDialog(this);}Status("可以继续正常登录游戏。");
            }catch{Status("连接未能完成，请检查网络后重试。",true);}finally{SetBusy(false);}
        }
        async Task LoginAndStart() {
            string diagnosticAttempt=DiagnosticService.BeginAttempt();
            if(!File.Exists(clientPath)) {DiagnosticService.Update(diagnosticAttempt,"client_not_selected",null,true);Status("请先选择客户端目录。",true);return;}
            string name=nameBox.Text.Trim(),password=PasswordForAuth();
            if(name.Length==0||(token==null&&password.Length==0)){DiagnosticService.Update(diagnosticAttempt,"credentials_missing",null,true);Status("请输入账号和密码。",true);return;}
            SetBusy(true);Status("正在登录…");string config=null;
            try {
                DiagnosticService.Update(diagnosticAttempt,"login");
                Dictionary<string,object> request=token!=null&&tokenName==name&&password.Length==0?new Dictionary<string,object>{{"op","resume"},{"name",name},{"token",token}}:new Dictionary<string,object>{{"op","login"},{"name",name},{"password",password}};
                var result=await Task.Run(()=>Program.Api(request));
                if(!Program.Ok(result)){DiagnosticService.Update(diagnosticAttempt,"authentication_failed",null,true);token=null;Save();Status(Program.Error(result),true);return;}
                CommitAuthenticated(result,name,password);
                DiagnosticService.Update(diagnosticAttempt,"component_update");
                string root;try{root=await Task.Run(()=>Program.EnsurePayload(Progress));DiagnosticService.BindRuntime(diagnosticAttempt,root);}catch(Exception error){DiagnosticService.ComponentFailure(diagnosticAttempt,error);Status("运行组件更新未完成，可打开“诊断与反馈”提交本次记录；原环境已保留。",true);return;}
                string logs=Path.Combine(Program.DataRoot,"logs");Directory.CreateDirectory(logs);
                config=Path.Combine(Program.DataRoot,"sessions",Guid.NewGuid().ToString("N")+".json");
                Program.PrivateWrite(config,Program.Json.Serialize(new Dictionary<string,object>{{"host",Program.Host},{"port",19400},{"name",name},{"token",token},{"certificate_sha256",Program.Pin}}));
                string args=Program.Quote(Path.Combine(root,"tools","launch_friends_client.py"))+" --config "+Program.Quote(config)+" --client "+Program.Quote(clientPath)+" --allow-client-variants";
                Status("正在准备客户端，允许不同文件版本…");
                DiagnosticService.Update(diagnosticAttempt,"preflight");
                string checkLog=DiagnosticService.LogPath(diagnosticAttempt,"client-check.log");
                int check=await Task.Run(()=>Program.RunPython(root,args+" --check",checkLog));
                if(check!=0){DiagnosticService.Update(diagnosticAttempt,"preflight_failed",check,true);ShowLaunchFailure(checkLog);return;}
                Status("正在启动游戏，正常退出游戏后可再次登录。");
                DiagnosticService.Update(diagnosticAttempt,"game_running");
                string launchLog=DiagnosticService.LogPath(diagnosticAttempt,"game-launch.log");
                int code=await Task.Run(()=>Program.RunPython(root,args,launchLog));
                DiagnosticService.Update(diagnosticAttempt,code==0?"game_exit":"game_failed",code,true);
                if(code==0){MotionEffects.Feedback(login,true);Status("游戏已退出，可以再次启动。");}else ShowLaunchFailure(launchLog);
            }catch {DiagnosticService.Update(diagnosticAttempt,"launcher_error",null,true);Status("连接或启动未能完成，请检查网络后重试。",true);}finally {if(config!=null&&File.Exists(config))File.Delete(config);SetBusy(false);}
        }
        async Task OpenDiagnostics(){
            if(openingDiagnostics)return;openingDiagnostics=true;diagnostics.Enabled=false;MotionEffects.Busy(diagnostics,true);
            try{
                string root=ComponentRuntime.PreparedRoot;
                if(root==null)root=await Task.Run(()=>{try{return ComponentRuntime.Available();}catch{return null;}});
                string selectedClient=clientPath,account=tokenName,credential=token;
                using(var dialog=new DiagnosticsForm(DiagnosticService.Choices(),(id,note)=>DiagnosticService.Generate(root,id,note,selectedClient,account,credential),bundle=>DiagnosticService.Upload(root,bundle,selectedClient,account,credential),!String.IsNullOrEmpty(credential)&&!String.IsNullOrEmpty(account))){dialog.ShowDialog(this);}
            }catch {Status("诊断工具暂未准备完成，请稍后重试。",true);}finally{openingDiagnostics=false;MotionEffects.Busy(diagnostics,false);diagnostics.Enabled=true;}
        }
        void ShowLaunchFailure(string logPath) {
            string reason=Program.LaunchFailure(logPath);Status(reason,true);
            MessageBox.Show(this,reason+"\n\n可点击登录器下方“诊断与反馈”，生成并上传本次报告。\n诊断日志：\n"+logPath,"朋友服",MessageBoxButtons.OK,MessageBoxIcon.Information);
        }
    }
    class TutorialRecoveryForm:ProofForm {
        protected override bool WindowResizable {get{return false;}}
        readonly string accountName,credential;
        readonly ListBox roster=new ListBox(); readonly Label status=new Label();
        readonly Button previous=new SoftButton(),next=new SoftButton(),refresh=new SoftButton(),confirm=new SoftButton();
        readonly Dictionary<string,string> operations=new Dictionary<string,string>();
        int offset=0;int? nextOffset;bool busy;
        class Choice {
            public Dictionary<string,object> Data;
            public override string ToString(){return Convert.ToString(Data["name"])+" · "+Role(Convert.ToInt32(Data["unit_type"]))+" · 魔奇 → 新手起点";}
        }
        static string Role(int role){return role==13?"菈比":role==14?"诺亚":"莉缇娅";}
        public TutorialRecoveryForm(string name,string token,bool test=false){
            accountName=name;credential=token;proofMode=test;Text="恢复新手起点";ClientSize=new Size(680,380);MinimumSize=Size;
            Font=new Font("Microsoft YaHei UI",9);BackColor=Theme.Canvas;ForeColor=Theme.Ink;StartPosition=FormStartPosition.CenterParent;
            var header=new TableLayoutPanel{Dock=DockStyle.Top,Height=56,ColumnCount=2,RowCount=1,Margin=Padding.Empty,Padding=new Padding(18,12,8,12),BackColor=Color.White};header.RowStyles.Add(new RowStyle(SizeType.Percent,100));
            header.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));header.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,108));
            var title=new Label{Text="恢复新手起点",Dock=DockStyle.Fill,Margin=Padding.Empty,TextAlign=ContentAlignment.MiddleLeft,Font=new Font(Font.FontFamily,12,FontStyle.Bold)};header.Controls.Add(title,0,0);header.Controls.Add(WindowControls(false),1,0);Controls.Add(header);BindWindowDrag(header);BindWindowDrag(title);
            var body=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=4,Padding=new Padding(20,14,20,14)};
            body.RowStyles.Add(new RowStyle(SizeType.Absolute,34));body.RowStyles.Add(new RowStyle(SizeType.Percent,100));body.RowStyles.Add(new RowStyle(SizeType.Absolute,46));body.RowStyles.Add(new RowStyle(SizeType.Absolute,44));
            body.Controls.Add(new Label{Text="选择需要移回原新手起点的旧角色。请先正常退出游戏。",Dock=DockStyle.Fill},0,0);
            roster.Dock=DockStyle.Fill;roster.IntegralHeight=false;roster.ItemHeight=30;roster.Font=new Font(Font.FontFamily,10);roster.AccessibleName="可恢复的角色";roster.SelectedIndexChanged+=delegate{UpdateButtons();};body.Controls.Add(roster,0,1);
            status.Dock=DockStyle.Fill;status.ForeColor=Theme.Muted;status.Padding=new Padding(0,8,0,0);body.Controls.Add(status,0,2);
            var actions=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=4,Margin=Padding.Empty};for(int i=0;i<4;i++)actions.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,25));
            previous.Text="上一页";next.Text="下一页";refresh.Text="刷新角色";confirm.Text="恢复起点";confirm.BackColor=Theme.Coral;confirm.ForeColor=Color.White;
            var buttons=new[]{previous,next,refresh,confirm};for(int i=0;i<4;i++){buttons[i].Dock=DockStyle.Fill;buttons[i].Margin=new Padding(i==0?0:8,0,0,0);actions.Controls.Add(buttons[i],i,0);}body.Controls.Add(actions,0,3);Controls.Add(body);body.BringToFront();
            previous.Click+=async delegate{await LoadPage(Math.Max(0,offset-4));};next.Click+=async delegate{if(nextOffset.HasValue)await LoadPage(nextOffset.Value);};refresh.Click+=async delegate{await LoadPage(offset);};confirm.Click+=async delegate{await Confirm();};
            FormClosing+=delegate(object sender,FormClosingEventArgs e){if(busy)e.Cancel=true;};Shown+=async delegate{if(!proofMode)await LoadPage(0);};UpdateButtons();
        }
        void UpdateButtons(){previous.Enabled=!busy&&offset>0;next.Enabled=!busy&&nextOffset.HasValue;refresh.Enabled=!busy;confirm.Enabled=!busy&&roster.SelectedItem!=null;roster.Enabled=!busy;UseWaitCursor=busy;}
        Dictionary<string,object> Request(string operation){return new Dictionary<string,object>{{"op",operation},{"name",accountName},{"token",credential}};}
        void BindRows(Dictionary<string,object> result,int page){
            var rows=new List<Choice>();var values=result["characters"] as System.Collections.IEnumerable;if(values==null)throw new IOException("Invalid response");
            foreach(var value in values){var row=value as Dictionary<string,object>;if(row==null||row.Count!=6||rows.Count==4)throw new IOException("Invalid row");
                long uid=Convert.ToInt64(row["uid"]);int type=Convert.ToInt32(row["unit_type"]),town=Convert.ToInt32(row["target_town"]);string name=Convert.ToString(row["name"]),version=Convert.ToString(row["version"]);
                if(uid<1001||uid>9007199254740991L||type<13||type>15||town!=(type==13?20011:type==14?20012:20014)||Convert.ToInt32(row["from_town"])!=20000||name.Length<2||name.Length>12||!System.Text.RegularExpressions.Regex.IsMatch(version,"^[0-9a-f]{64}$"))throw new IOException("Invalid row");rows.Add(new Choice{Data=new Dictionary<string,object>(row)});
            }
            int? candidateNext=result["next_offset"]==null?(int?)null:Convert.ToInt32(result["next_offset"]);if(candidateNext.HasValue&&(candidateNext.Value!=page+4||candidateNext.Value>100000))throw new IOException("Invalid page");
            nextOffset=candidateNext;offset=page;roster.Items.Clear();foreach(var row in rows)roster.Items.Add(row);if(rows.Count>0)roster.SelectedIndex=0;
            status.Text=rows.Count>0?"请选择一个角色，再确认恢复。":nextOffset.HasValue?"本页没有可恢复角色，可以查看下一页。":"没有可恢复的旧角色。";UpdateButtons();
        }
        async Task LoadPage(int page){if(busy)return;busy=true;UpdateButtons();status.Text="正在读取角色…";
            try{var request=Request("tutorial_recovery_preview");request.Add("offset",page);var result=await Task.Run(()=>Program.Api(request));if(!Program.Ok(result)){status.Text=Program.Error(result);return;}BindRows(result,page);}
            catch{status.Text="读取未能完成，请检查网络后刷新。";}finally{busy=false;UpdateButtons();}}
        internal Dictionary<string,object> ConfirmationRequest(){
            var selected=roster.SelectedItem as Choice;if(selected==null)throw new InvalidOperationException();var row=selected.Data;string key=Convert.ToString(row["uid"])+":"+Convert.ToString(row["version"]),operation;
            if(!operations.TryGetValue(key,out operation)){operation=Guid.NewGuid().ToString();operations.Add(key,operation);}
            var request=Request("tutorial_recovery_confirm");request.Add("uid",Convert.ToInt64(row["uid"]));request.Add("version",row["version"]);request.Add("operation_id",operation);return request;
        }
        internal string ConfirmationText(){var selected=(Choice)roster.SelectedItem;return "将“"+Convert.ToString(selected.Data["name"])+"”移回"+Role(Convert.ToInt32(selected.Data["unit_type"]))+"的新手起点。等级、物品和任务保持不变。请先正常退出此账号的游戏。";}
        async Task Confirm(){if(busy||roster.SelectedItem==null)return;
            if(MessageBox.Show(this,ConfirmationText(),"恢复新手起点",MessageBoxButtons.OKCancel,MessageBoxIcon.Question)!=DialogResult.OK)return;
            var request=ConfirmationRequest();busy=true;UpdateButtons();status.Text="正在备份并恢复起点…";
            try{var result=await Task.Run(()=>Program.Api(request));if(!Program.Ok(result)){status.Text=Program.Error(result);return;}status.Text="已恢复新手起点，下次正常登录生效。";MessageBox.Show(this,status.Text,"恢复完成",MessageBoxButtons.OK,MessageBoxIcon.Information);}
            catch{status.Text="结果尚未确认，请重试同一角色以查询结果。";}finally{busy=false;UpdateButtons();}
        }
        internal void BindRowsForTest(Dictionary<string,object> result,int page){if(!proofMode)throw new InvalidOperationException();BindRows(result,page);}
        internal void SelectForTest(int index){if(!proofMode)throw new InvalidOperationException();roster.SelectedIndex=index;}
    }
    partial class RegisterForm:ProofForm {
        protected override bool WindowResizable {get{return false;}}
        TextBox account=new TextBox(),password=new TextBox(),confirm=new TextBox();
        public string Account {get{return account.Text.Trim();}} public string Password {get{return password.Text;}}
        public RegisterForm(string name) {
            var submit=BuildRegistration(name);
            submit.Click+=delegate {if(password.Text!=confirm.Text){MotionEffects.Feedback(submit,false);MessageBox.Show(this,"两次输入的密码不一致。","请检查");return;}if(!System.Text.RegularExpressions.Regex.IsMatch(Account,"^[a-z][a-z0-9_]{2,23}$")||password.Text.Length<8){MessageBox.Show(this,"请按提示填写账号和密码。","请检查");return;}DialogResult=DialogResult.OK;Close();};
        }
    }
}

