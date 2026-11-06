using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class LoginRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-login-reconnect-20261031-v1",LocalPayload="620de182193d3dfaf2bd8856c07d293a68fb72b6c250a7e2db098830251f72ab",LocalEnvelope="f1ac107e3e4d92f6e15439a8bd3c7c7f52733e33be81719c39c5485695001a1b",LocalMetadata="09735636edab7529c5f745b890a801956357dc72d4932ba9d3a8bf306610d792",BootstrapHash="cef9c18e6ce4e69b38f6d36b4c1bf9d750222ed08119862d01bd7ae689d98f6c",LocalResource="ElsFriends.LoginLocalRuntimeFiles",BootstrapResource="ElsFriends.LoginLocalBootstrap";
  internal const string FriendsPayload="e050172f6ba9dde3bb91124cc295b78ec4a1fd32c19308913f722e7d4659fe37",FriendsEnvelope="eedd59cb6febf5333c7c67578a5d762e74df1acd8069c6f24d103f3befbc05ab",FriendsProfileHash="04f08ad5c11f538538c3d3633e8c3bb793ace978e962f5ad33a7ebcd4728ac6e",FriendsResource="ElsFriends.LoginFriendsRuntimeFiles";
  internal const int LocalCount=1800,FriendsCount=1785;
  internal static void RequireLocal(){NextAccessoryCohort.RequireLocal();}
  internal static bool RequireCurrentDirection(Dictionary<string,object> p,LocalCohortSnapshot source){
   object value;if(!p.TryGetValue("release",out value)||!(value is string))return false;
   string release=(string)value;if(release!=ManagedRelease&&!release.StartsWith(ManagedRelease+"-guarded-",StringComparison.Ordinal))return false;
   if(!NextAccessoryCohort.IsSource(source))throw new IOException("Current world LOCAL source cannot be downgraded");
   if(Convert.ToString(p["source_release"])!=NextAccessoryCohort.Release||Convert.ToString(p["source_formal_manifest_sha256"])!=NextAccessoryCohort.FormalHash)throw new IOException("World LOCAL source identity changed");
   if(release!=ManagedRelease){if(!System.Text.RegularExpressions.Regex.IsMatch(release,"^"+System.Text.RegularExpressions.Regex.Escape(ManagedRelease)+"-guarded-[a-f0-9]{12}$")||Convert.ToString(p["recovery_of"])!=ManagedRelease)throw new IOException("Unknown world recovery identity");foreach(string k in new[]{"recovery_only","complete_C3_reader_and_data","all_three_guards","selection_reader_compatible_recovery","all_five_selection_readers_retained","new_722531_operations_paused"})if(!p.TryGetValue(k,out value)||!Object.Equals(value,true))throw new IOException("Incomplete world recovery");}
   return true;
  }
 }
}
