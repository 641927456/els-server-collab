"""Pin only the isolated v2 candidate and retain its exact composed source."""
from pathlib import Path
import hashlib,json,sys
H=Path(__file__).resolve().parent;C=H.parent/'repair-v9/candidate'
sys.dont_write_bytecode=True;sys.path[:0]=[str(C/'tools'),str(C),str(C/'tools/pylibs')]
from native_cache_sync import compose
from native_send_serialization import EXE_SHA
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for name in ['native_cache_sync.py','native_send_serialization.py','probe_updated_client.py']:
 p=C/'tools'/name;compile(p.read_bytes(),str(p),'exec')
raw=(C/'tools/native_send_serialization.js').read_text('utf-8');core=(H/'native_crypto_lock.js').read_text('utf-8');core=core[core.index('function installElsNativeCryptoLock'):]
assert raw.startswith('// Native crypto core is retained until the owned game exits; no hot unload.\n'+core+'\n')
image=Path('G:/els/analysis/client-6c6b5180/x2-runtime.bin').read_bytes();text=compose(image,EXE_SHA,(C/'tools/trace_dx11_login.js').read_text('utf-8'))
assert text.count('elsObserveNativeSend(')==6 and text.count('elsObserveNativeField(')==6
assert text.count('__ARTIFACT_RESTORE__')==text.count('__SHOP_BRIDGE__')==1
assert text.count('Interceptor.replaceFast(module.base.add(0x3b7d620),')==1
assert text.count('Interceptor.replaceFast(module.base.add(0x3b7d860),')==1
for name in ['module','game','arM','ebM']:
 for rva in ['0x682d80','0x30d0660']:assert 'Interceptor.attach('+name+'.base.add('+rva+'),'not in text
assert text.count('const sender=observeAt(module.base.add(0x682d80)),field=observeAt(module.base.add(0x30d0660));')==1
assert text.count('Interceptor.attach(address,{')==1
assert 'startup_shop=session.create_script'not in(C/'tools/probe_updated_client.py').read_text('utf-8')
(H/'composed-native-login.js').write_bytes(text.encode())
p=C/'tools/client_compatibility_profiles.json';v=json.loads(p.read_bytes());names=['tools/native_cache_sync.py','tools/native_send_serialization.py','tools/native_send_serialization.js','tools/probe_updated_client.py']
for profile in v['profiles']:
 if profile.get('executable_sha256')==EXE_SHA:
  for name in names:profile['artifacts'][name]=sha(C/name)
p.write_bytes((json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode())
result={'ok':True,'native_release_qualified':False,'composed_sha256':sha(H/'composed-native-login.js'),'embedded_core_source_sha256':sha(H/'native_crypto_lock.js'),'sender_physical_JS_listeners':1,'town_frame_physical_JS_listeners':1,'native_fast_replacements':2,'sender_production_logical_observers':5,'town_frame_possible_logical_registration_sites':5,'artifact_and_complete_shop_in_main_realm':True,'files':{n:sha(C/n)for n in [*names,'tools/client_compatibility_profiles.json']}}
(H/'native-composition.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps(result))
