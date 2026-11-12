using System;
using System.IO;
using System.Net;
using System.Text.RegularExpressions;

namespace ElsFriends {
    // Public, anonymous release downloads. Authenticity remains bound to the
    // publisher's RSA signature and signed size/SHA256, independent of GitHub.
    static class GitHubUpdates {
        internal const string Root="https://github.com/641927456/els-launcher-updates/releases/";
        internal static string Address(string name,string runtimeHash=null) {
            if(name=="latest.json")return Root+"latest/download/latest.json";
            var exe=Regex.Match(name??"","^v([0-9]+)-([a-f0-9]{16})\\.exe$");
            if(exe.Success)return Root+"download/launcher-v"+exe.Groups[1].Value+"-"+exe.Groups[2].Value+"/"+name;
            var runtime=Regex.Match(name??"","^runtime-([a-f0-9]{64})\\.zip$");
            if(runtime.Success)return Root+"download/runtime-"+runtime.Groups[1].Value+"/"+name;
            var chunk=Regex.Match(name??"","^chunk-([a-f0-9]{64})\\.zip$");
            if(chunk.Success&&Regex.IsMatch(runtimeHash??"","^[a-f0-9]{64}$"))return Root+"download/runtime-"+runtimeHash+"/"+name;
            throw new IOException("Unknown signed update asset");
        }
        internal static bool Allowed(Uri uri) {
            if(uri==null||!uri.IsAbsoluteUri||uri.Scheme!="https"||uri.Port!=443||uri.UserInfo.Length!=0||uri.Fragment.Length!=0)return false;
            if(uri.Host=="github.com")return uri.AbsolutePath.StartsWith("/641927456/els-launcher-updates/releases/",StringComparison.Ordinal)&&uri.Query.Length==0;
            return uri.Host=="release-assets.githubusercontent.com"||uri.Host=="objects.githubusercontent.com";
        }
        internal static HttpWebResponse Open(string name,string runtimeHash=null) {
            ServicePointManager.SecurityProtocol=SecurityProtocolType.Tls12;
            var address=new Uri(Address(name,runtimeHash));
            for(int hop=0;hop<5;hop++) {
                if(!Allowed(address))throw new IOException("Update redirect outside release hosts");
                var request=(HttpWebRequest)WebRequest.Create(address);
                request.AllowAutoRedirect=false;request.Timeout=12000;request.ReadWriteTimeout=30000;request.Proxy=null;
                request.UserAgent="ElsFriendsLauncher/"+AutoUpdate.Version;request.Headers[HttpRequestHeader.CacheControl]="no-cache";
                // Use Windows chain and hostname validation; no certificate
                // callback, shared trust override, token or game-host fallback.
                var response=(HttpWebResponse)request.GetResponse();
                if(response.StatusCode==HttpStatusCode.OK)return response;
                int status=(int)response.StatusCode;string location=response.Headers[HttpResponseHeader.Location];response.Dispose();
                if((status!=301&&status!=302&&status!=303&&status!=307&&status!=308)||String.IsNullOrEmpty(location))throw new IOException("Release asset unavailable");
                address=new Uri(address,location);
            }
            throw new IOException("Too many update redirects");
        }
    }
}
