using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Security.Principal;

namespace ElsFriends {
    // Restart only this launcher; credentials remain in the existing user store.
    static class LaunchElevation {
        internal const string Marker="ELS_LAUNCH_ELEVATION_REQUIRED: 740";

        internal static bool Required(string logPath) {
            foreach(string line in File.ReadLines(logPath))
                if(String.Equals(line,Marker,StringComparison.Ordinal))return true;
            return false;
        }

        internal static bool IsElevated() {
            using(var identity=WindowsIdentity.GetCurrent())
                return new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator);
        }

        internal static ProcessStartInfo StartInfo() {
            string launcher=Assembly.GetExecutingAssembly().Location;
            using(var parent=Process.GetCurrentProcess())
                return new ProcessStartInfo(launcher,"--updated-parent "+parent.Id+LaunchMode.RestartArguments) {
                    UseShellExecute=true,
                    Verb="runas",
                    WorkingDirectory=Path.GetDirectoryName(launcher)
                };
        }

        internal static void Restart() {
            using(var process=Process.Start(StartInfo()))
                if(process==null)throw new InvalidOperationException("Windows did not start the elevated launcher");
        }
    }
}
