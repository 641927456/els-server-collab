"""Prepare only the private sender-dispatcher candidate, never formal channels."""
from pathlib import Path
import hashlib,json,sys
H=Path(__file__).resolve().parent;C=H.parent/'repair-v9/candidate'
sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'tools'),str(C/'tools/pylibs')]
from native_cache_sync import compose
from native_send_serialization import EXE_SHA
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
image=Path('G:/els/analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
for name in ('native_cache_sync.py','native_send_serialization.py','probe_updated_client.py'):
 p=C/'tools'/name;compile(p.read_bytes(),str(p),'exec')
text=compose(image,EXE_SHA,(C/'tools/trace_dx11_login.js').read_text('utf-8'))
assert text.count('elsObserveNativeSend(')==6  # five observers plus API declaration
assert text.count('__ARTIFACT_RESTORE__')==1
assert text.count('Interceptor.attach(module.base.add(0x682d80),')==2
assert 'Interceptor.attach(game.base.add(0x682d80),' not in text
assert 'Interceptor.attach(arM.base.add(0x682d80),' not in text
assert text.index('prepareElsNativeSendSerialization()();')<text.index('elsObserveNativeSend(',text.index('prepareElsNativeSendSerialization()();'))
(H/'composed-native-login.js').write_text(text,encoding='utf-8')
p=C/'tools/client_compatibility_profiles.json';v=json.loads(p.read_bytes())
names=('tools/native_cache_sync.py','tools/native_send_serialization.py','tools/native_send_serialization.js','tools/probe_updated_client.py')
for profile in v['profiles']:
 if profile.get('executable_sha256')==EXE_SHA:
  for name in names:profile['artifacts'][name]=sha(C/name)
p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
result={'ok':True,'native_release_qualified':False,'composed_sha256':sha(H/'composed-native-login.js'),'physical_sender_registration_sites':2,'production_sender_observer_sites':5,'artifact_moved_to_main_script':True,'files':{n:sha(C/n)for n in (*names,'tools/client_compatibility_profiles.json')}}
(H/'native-composition.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
