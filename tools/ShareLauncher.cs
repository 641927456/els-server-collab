using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class ShareLauncher
{
    [STAThread]
    private static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(root, "python", "pythonw.exe");
        string script = Path.Combine(root, "本地测试启动器.pyw");
        try
        {
            if (!File.Exists(python) || !File.Exists(script))
                throw new FileNotFoundException("请先完整解压分享包，再运行本地测试启动器。");
            if (args.Length == 1 && args[0] == "--verify-entry") return 0;
            using (OpenFileDialog dialog = new OpenFileDialog())
            {
                dialog.Title = "选择你自己的客户端 data\\x2_dx11.exe";
                dialog.Filter = "艾尔之光 DX11 客户端 (x2_dx11.exe)|x2_dx11.exe";
                dialog.CheckFileExists = true;
                dialog.Multiselect = false;
                if (dialog.ShowDialog() != DialogResult.OK) return 0;
                if (!String.Equals(Path.GetFileName(dialog.FileName), "x2_dx11.exe", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("请选择客户端 data 目录中的 x2_dx11.exe。");
                ProcessStartInfo info = new ProcessStartInfo(python);
                info.Arguments = "-B -X utf8 \"" + script + "\" --client \"" + dialog.FileName + "\"";
                info.WorkingDirectory = root;
                info.UseShellExecute = false;
                info.CreateNoWindow = true;
                info.WindowStyle = ProcessWindowStyle.Hidden;
                Process.Start(info);
                return 0;
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "艾尔之光 · 协作本地测试", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }
}
