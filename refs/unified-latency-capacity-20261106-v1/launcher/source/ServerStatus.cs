using System;
using System.Collections.Generic;
using System.Drawing;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace ElsFriends {
    partial class MainForm {
        readonly System.Windows.Forms.Timer serverStatusTimer = new System.Windows.Forms.Timer {Interval=10000};
        Func<string,string,Dictionary<string,object>> serverStatusQuery = Program.ServerStatus;
        bool checkingServerStatus;
        int serverStatusGeneration;

        void InitializeServerStatus() {
            SetServerAvailability(null);
            serverStatusTimer.Tick += async delegate {await RefreshServerStatus();};
            Disposed += delegate {serverStatusGeneration++;serverStatusTimer.Dispose();};
        }

        void SetServerAvailability(bool? online) {
            string target = LaunchMode.Local ? "本机" : "朋友测试服";
            server.Text = (online == null ? "正在检查服务器" : online.Value ? "服务器在线" : "暂时无法连接") + " · " + target;
            server.ForeColor = online == null ? Theme.Muted : online.Value ? Color.FromArgb(63,157,134) : Theme.Coral;
        }

        async void RefreshSelectedServerStatus() {
            if(IsDisposed || Disposing)return;
            serverStatusGeneration++;
            SetServerAvailability(null);
            await RefreshServerStatus();
        }

        async Task RefreshServerStatus() {
            if(checkingServerStatus || IsDisposed || Disposing)return;
            checkingServerStatus = true;
            try {
                int generation;
                do {
                    generation = serverStatusGeneration;
                    string host = Program.Host;
                    bool online;
                    try {
                        string pin = Program.Pin;
                        var result = await Task.Run(() => serverStatusQuery(host, pin));
                        online = Program.Ok(result);
                    } catch {
                        online = false;
                    }
                    if(IsDisposed || Disposing)return;
                    if(generation == serverStatusGeneration)SetServerAvailability(online);
                    // A mode switch or launch failure requests a new observation;
                    // finish the old request before checking the selected endpoint.
                } while(generation != serverStatusGeneration);
            } finally {
                checkingServerStatus = false;
            }
        }
    }
}
