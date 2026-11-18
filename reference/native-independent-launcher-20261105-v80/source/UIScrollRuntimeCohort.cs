using System;
using System.IO;
using System.Collections.Generic;
namespace ElsFriends {
 static class UIScrollRuntimeCohort {
  internal const string ManagedRelease="local-git-first-run-atlas-scroll-support-20261101-v1",LocalPayload="3abb8aee941cefbe81e66500f44b8c395b3f87ec4d85dac2338f9fc63aa0b5ad",LocalEnvelope="f20f3317a6ca1d2eaefa27012985aed001632a1d97f5fe012902d94721b7900e",LocalMetadata="9182f83bbd7c6a9a83305f27aa99d26ba952c3140312b4bc1d5415072cc16d1d",BootstrapHash="8549bb4e6136e2f8913b130713fc2d308bc52022ec0517bd2224eb2293395e60",LocalResource="ElsFriends.UIScrollLocalRuntimeFiles",BootstrapResource="ElsFriends.UIScrollLocalBootstrap";
  internal const string FriendsPayload="6a766dd63217e4b1851ad8a85c751efee497acf2751e9de298442cc7d7709ba1",FriendsEnvelope="8426a60a8f9c1017d9400ebbfceaa9e247f18b303e328a82dd3cc2e542b6730e",FriendsProfileHash="2e454cf89dbfec8c02008a18881be2b66cc75a98cc6ac66fa623a1d135dc9f76",FriendsResource="ElsFriends.UIScrollFriendsRuntimeFiles";
  internal const int LocalCount=1934,FriendsCount=2152;
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
