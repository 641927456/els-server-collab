"""Verify the actual V43 public source, signed cohorts and unique predecessor."""
from pathlib import Path
import base64,hashlib,importlib.util,json,re,sys
from xml.etree import ElementTree
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'launchers/friends-v43';OLD=ROOT/'launchers/friends-v42'
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def require(value,message):
 if not value:raise ValueError(message)
def verify(path,key,runtime=True):
 wrapper=read(path);raw=base64.b64decode(wrapper['payload'],validate=True);signature=base64.b64decode(wrapper['signature'],validate=True)
 xml=ElementTree.fromstring(key);num=lambda n:int.from_bytes(base64.b64decode(xml.findtext(n)),'big')
 n,e=num('Modulus'),num('Exponent');width=(n.bit_length()+7)//8
 require(len(signature)==width and int.from_bytes(signature,'big')<n,'Invalid RSA size')
 actual=pow(int.from_bytes(signature,'big'),e,n).to_bytes(width,'big')
 suffix=bytes.fromhex('3031300d060960864801650304020105000420')+hashlib.sha256(raw).digest()
 require(actual==b'\0\1'+b'\xff'*(width-len(suffix)-3)+b'\0'+suffix,'Invalid RSA signature')
 d=json.loads(raw);require((d['schema'],d['product'],d['channel'])==(1,'ElsFriends','friends'),'Wrong signed channel')
 if runtime:require(d['kind']=='runtime-files','Wrong signed kind')
 return d
def main():
 require(sha(A/'source-lock.json')=='015f3c9edc6a671d0957a8831c8adb7e0e3342344e80abb4cf2b19166d9e0cbc','Actual source lock changed')
 spec=importlib.util.spec_from_file_location('verified_v43_build',A/'build.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 lock,files,_=m.inputs();require(len(files)==25 and lock['V']==43,'V43 input set changed')
 key=re.search(r'PublicKey = "([^"]+)"',(A/'AutoUpdate.cs').read_text('utf-8-sig')).group(1)
 oldkey=re.search(r'PublicKey = "([^"]+)"',(OLD/'AutoUpdate.cs').read_text('utf-8-sig')).group(1);require(key==oldkey,'Publisher public key changed')
 friend=verify(A/'runtime-files.signed.json',key);local=verify(A/'local-runtime-files.signed.json',key);legacy=verify(A/'legacy-local-runtime-files.signed.json',key)
 release=verify(A/'release.signed.json',key,False);declared=read(A/'release.json')
 require(release['version']==declared['V']==43 and release['sha256']==declared['sha256']==lock['actual_compiled_EXE_sha256'],'Actual EXE release differs')
 require(release['size']==declared['size'],'Actual EXE size differs')
 require(sha(A/'runtime-files.signed.json')==sha(OLD/'runtime-files.signed.json'),'Friends signed runtime changed')
 require(len(friend['files'])==1764 and friend['archive']['sha256']==declared['payload_sha256'],'Friends payload changed')
 require(len(local['files'])==len(legacy['files'])==1779,'LOCAL member count changed')
 require(local['archive']['sha256']==declared['local_payload_sha256']=='c2479938972ae6f9c6f3747d2348f28473dbaa2635ee93e16c1b9239e309f86e','New LOCAL payload differs')
 require(sha(A/'legacy-local-runtime-files.signed.json')==sha(OLD/'local-runtime-files.signed.json'),'Legacy resource changed')
 require(sha(A/'legacy-local-bootstrap.py')==sha(OLD/'local_bootstrap.py'),'Legacy bootstrap changed')
 require(sha(A/'local_bootstrap.py')=='24f1bde4e963528db97a8dbbd477d9ff7ae3c063a924f8b2fe820621523a7fe0','Managed consumer changed')
 require(sha(A/'local_updater.py')==sha(OLD/'local_updater.py'),'Original updater changed')
 rows={r['path']:r for r in local['files']};previous={r['path']:r for r in legacy['files']}
 require(set(rows)==set(previous),'Signed member set changed')
 diff={p for p in rows if rows[p]!=previous[p]}
 require(diff=={'els_server/storage/characters.py','els_server/storage/seal_quests.py','els_server/storage/career_shop.py','els_server/protocol/local_messages.py','els_server/protocol/dungeon_messages.py','local-bootstrap-source.json'},'Unexpected signed source delta')
 require(rows['local-bootstrap-source.json']['sha256']==sha(A/'local-bootstrap-source.json')=='0a2e4071eb897b8e0b6b210152d305b28bbe571366b95b86f8ed0b5dec54432c','Managed metadata changed')
 meta=read(A/'local-bootstrap-source.json');oldmeta=read(OLD/'local-bootstrap-source.json')
 require(meta['upgrade_from']['old_signed_envelope_sha256']==sha(A/'legacy-local-runtime-files.signed.json'),'Unique predecessor differs')
 for k in ('support_overrides','support_additions','generated_config_source_sha256'):require(meta[k]==oldmeta[k],'Existing bootstrap support changed')
 for prefix,snapshot,expected in [('Legacy','legacy-accepted-source-selection.json','77fb1412039711eaba1160f03f96cdd61bfb3fdde54df3c08491281f0ac448b9'),('Identity','accepted-source-selection.json','27c1895d03893cb5ffb79b4a7a84ebcedd501f25efb981fe2a0b5b3a16cbffe8')]:
  selection=read(A/snapshot);profile_path=ROOT/selection['profile'];require(sha(profile_path)==expected,'Pinned cohort profile differs')
  profile=read(profile_path);formal={r['path']:r for r in profile['channels']['local']['files']}
  normalized=[{k:formal[p][k] for k in ('path','size','sha256')} for p in sorted(formal)]
  digest=hashlib.sha256(json.dumps(normalized,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
  selected=oldmeta if prefix=='Legacy' else meta
  require(len(formal)==selected['source_file_count']==1325 and digest==selected['source_files_sha256'],'Complete cohort source index differs')
  require(selection['accepted']['local']['formal_manifest_sha256']==selected['source_formal_manifest_sha256'],'Cohort formal identity differs')
 for path,name in [('tools/launch_client.py','launch_client.py'),('tools/local_fresh_state.py','local_fresh_state.py'),('tools/client_compatibility_profiles.json','client_compatibility_profiles.json')]:require(rows[path]['sha256']==sha(A/name),'Signed support source differs')
 require(lock['actual_compiled_resources']==7,'Actual resource count differs')
 print(json.dumps(dict(ok=True,V=43,native_inputs=25,signed_resources=7,RSA_envelopes_verified=4,cohort_profiles=2,source_files_each=1325,managed_upgrade_policy=True,compiled=False,published=False,game_started=False)))
if __name__=='__main__':main()
