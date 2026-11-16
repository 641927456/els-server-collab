using System;
using System.IO;

namespace ElsFriends {
    // Settings and remembered credentials retain their existing private profile.
    // Downloads, components, sessions and logs follow the selected game folder.
    static class ClientStorage {
        static string profileRoot,selectedClient;
        public static string ProfileRoot {get{return profileRoot??Program.DataRoot;}}
        public static string PreviousDataRoot {get{return profileRoot;}}
        public static string Resolve(string client) {
            if(String.IsNullOrWhiteSpace(client)||!Path.IsPathRooted(client)||
               !String.Equals(Path.GetFileName(client),"x2_dx11.exe",StringComparison.OrdinalIgnoreCase)||!File.Exists(client))
                throw new IOException("请先选择包含 x2_dx11.exe 的客户端目录，再下载运行组件。");
            string root=Path.GetFullPath(Path.Combine(Path.GetDirectoryName(Path.GetFullPath(client)),".els-runtime"));
            for(string path=root;!String.IsNullOrEmpty(path);path=Path.GetDirectoryName(path))
                if((Directory.Exists(path)||File.Exists(path))&&(File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0)
                    throw new IOException("运行组件目录不能经过链接，请选择实际客户端目录。");
            return root;
        }
        public static void Activate(string client) {
            string root=Resolve(client);
            if(profileRoot==null)profileRoot=Program.DataRoot;
            selectedClient=Path.GetFullPath(client);Program.DataRoot=root;
        }
        public static void ActivateSaved() {
            object value;var settings=Program.LoadSettings();
            if(settings.TryGetValue("client",out value)&&value is string&&File.Exists((string)value))Activate((string)value);
        }
        public static string Root {
            get {
                if(selectedClient==null)ActivateSaved();
                if(selectedClient==null)throw new IOException("请先选择客户端目录，运行组件将保存在该目录中。");
                return Resolve(selectedClient);
            }
        }
        public static string WritableRoot() {
            string root=Root;
            try {
                Directory.CreateDirectory(root);
                using(var file=new FileStream(Path.Combine(root,".write-"+Guid.NewGuid().ToString("N")),FileMode.CreateNew,FileAccess.Write,FileShare.None,4096,FileOptions.DeleteOnClose)){}
                return root;
            }catch(IOException error){throw new IOException("无法写入所选客户端目录，请检查该目录的写入权限和磁盘空间。",error);}
            catch(UnauthorizedAccessException error){throw new IOException("无法写入所选客户端目录，请检查该目录的写入权限。",error);}
        }
        public static void SelectProfile(string root) {
            profileRoot=null;selectedClient=null;Program.DataRoot=root;
        }
    }
}
