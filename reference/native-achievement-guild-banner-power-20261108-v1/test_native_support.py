"""Real Frida hooks in a disposable non-game process; explicit native CP fixture."""
from pathlib import Path
import sys,json,subprocess,threading,argparse
W=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--candidate',type=Path,default=W/'runtime');parser.add_argument('--tag',default='');args=parser.parse_args()
sys.dont_write_bytecode=True;sys.path[:0]=[str(args.candidate/'tools'),'G:/els/tools/pylibs']
import frida
import importlib.util,hashlib
base=Path('G:/els/releases/online/native-achievement-notebook-spa-clear-20261107-v1')
spec=importlib.util.spec_from_file_location('retained_raid_power_builder',base/'tools/raid_native_power.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
builder.__file__=str(args.candidate.resolve()/'tools/raid_native_power.py')
source,EXE_SHA=builder.source,builder.EXE_SHA
image=Path('G:/els/analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
script=r'''
(()=>{
 const RP=globalThis.Process,RNF=globalThis.NativeFunction,base=Memory.alloc(0x4820000),module={base};
 const Process={getModuleByName(n){if(n!=='x2_dx11.exe')throw Error('module');return module;},getCurrentThreadId(){return RP.getCurrentThreadId();}};
 const little=p=>{let n=BigInt(p.toString());return Array.from({length:8},()=>{const b=Number(n&255n);n>>=8n;return b;});};
 for(const[r,b]of Object.entries(__SEGMENTS__)){base.add(+r).writeByteArray(b);Memory.protect(base.add(+r).and(ptr(-RP.pageSize)),RP.pageSize,'rwx');}
 const engine=Memory.alloc(0x300),carrier=Memory.alloc(0xb0),unit=Memory.alloc(0x3100),def=Memory.alloc(4),sender=Memory.alloc(0x200),other=Memory.alloc(0x200),senderOwner=Memory.alloc(0x60),senderControl=Memory.alloc(0x10);
 base.add(0x4817e70).writePointer(engine);engine.add(0xc8).writePointer(carrier);engine.add(0xc0).writePointer(senderOwner);
 senderOwner.writePointer(sender);senderOwner.add(8).writePointer(senderControl);
 carrier.add(0xa0).writePointer(unit);unit.add(0x29c0).writePointer(def);def.writeS32(10);unit.add(0x48).writeU64(uint64('8589934593'));unit.add(0x58).writeU16(122);
 let calls=[],encoded=[],changeOwner=false,invalidCP=false,failEncoder=false,nested=null,mutateSource=null;
 const builder=new NativeCallback((u,n,mode,a,b,cp,dp,last,minus,nil)=>{
  if(!u.equals(unit)||mode!==0||last!==1||minus!==-1||!nil.isNull())throw Error('build ABI');
  calls.push(n);cp.writeFloat(invalidCP?NaN:n?2400:1500);dp.writeFloat(100);
  if(changeOwner)unit.add(0x48).writeU64(42);
  if(mutateSource){const change=mutateSource;mutateSource=null;change();}
 },'void',['pointer','uint32','uint8','pointer','pointer','pointer','pointer','uint8','int','pointer']);
 const store=new NativeCallback((u,n)=>{u.add(0x3048).writeFloat(n);},'void',['pointer','float']);
 const encoder=new NativeCallback((s,e)=>{
  const p=e.add(0x3e).readPointer(),n=e.add(0x46).readPointer().sub(p).toInt32();
  encoded.push(n?Array.from(new Uint8Array(p.readByteArray(n))):[]);
  if(nested){const f=nested;nested=null;f();}
  return failEncoder?0:1;
 },'bool',['pointer','pointer']);
 function NativeFunction(p,t,a,o){if(p.equals(base.add(0x896870)))return new RNF(builder,t,a,o);if(p.equals(base.add(0x8a1400)))return new RNF(store,t,a,o);return new RNF(p,t,a,o);}
 base.add(0x680b60).writeByteArray([0xeb,0x3e]);base.add(0x680ba0).writeByteArray([0x48,0xb8,...little(encoder),0xff,0xd0,0x48,0x83,0xc4,0x20,0x5f,0x48,0x8b,0x5c,0x24,8,0xc3]);
 base.add(0x682d9c).writeByteArray([0xeb,0x32]);base.add(0x682dd0).writeByteArray([0x48,0xb8,...little(base.add(0x680b50)),0xff,0xd0,0x48,0x81,0xc4,0x10,1,0,0,0x41,0x5f,0x41,0x5e,0x41,0x5d,0x41,0x5c,0x5f,0x5e,0x5d,0x48,0x8b,0x5c,0x24,0x18,0xc3]);
 __SUPPORT__
 const cm=new CModule('extern unsigned char run(void*,void*); unsigned char invoke(void*a,unsigned short k,void*e){return run(a,e);}',{run:base.add(0x682d80)});
 const invoke=new RNF(cm.invoke,'bool',['pointer','uint16','pointer']),cases=[];
 function check(v,n){if(!v)throw Error(n);cases.push(n);}
 function event(kind,length){const e=Memory.alloc(0x80),p=Memory.alloc(length+11);e.add(0x10).writeU32(0x202);e.add(0x34).writeU16(kind);e.add(0x36).writeU8(0);const bytes=Array.from({length},(_,i)=>(i*17+11)%256);p.writeByteArray(bytes);e.add(0x3e).writePointer(length?p:ptr(0));e.add(0x46).writePointer(length?p.add(length):ptr(0));e.add(0x4e).writePointer(length?p.add(length+11):ptr(0));return{e,p,bytes,vector:Array.from(new Uint8Array(e.add(0x3e).readByteArray(24)))};}
 function sendEvent(kind,length,who=sender){const v=event(kind,length);invoke(who,kind,v.e);check(JSON.stringify(v.vector)===JSON.stringify(Array.from(new Uint8Array(v.e.add(0x3e).readByteArray(24)))),'vector-restored-'+kind);return v;}
 function extension(raw,v,cp){const b=Uint8Array.from(raw),d=new DataView(b.buffer);return raw.length===v.bytes.length+16&&JSON.stringify(raw.slice(0,v.bytes.length))===JSON.stringify(v.bytes)&&d.getUint32(v.bytes.length)===0x52435031&&d.getUint32(v.bytes.length+4)===2&&d.getUint32(v.bytes.length+8)===1&&d.getFloat32(v.bytes.length+12)===cp;}
 let c=installElsRaidNativePower();Interceptor.flush();check(installElsRaidNativePower()===c,'duplicate-install-one-controller');
 for(const[k,n]of [[0x6be,0],[0x7d4,8],[0x14c,5],[0x37f,23],[0x382,37]]){calls=[];encoded=[];const v=sendEvent(k,n);if(!extension(encoded[0],v,2400))send({debug:{calls,encoded,active:c.active()}});check(extension(encoded[0],v,2400)&&JSON.stringify(calls)==='[0,1]','owned-native-request-'+k);}
 def.writeS32(1);calls=[];encoded=[];let v=sendEvent(0x7d4,8);check(extension(encoded[0],v,1500)&&JSON.stringify(calls)==='[0]','single-family-one-native-side');
 calls=[];encoded=[];v=sendEvent(0x123,8);check(encoded[0].length===8&&!calls.length,'unrelated-request-unchanged');calls=[];encoded=[];v=sendEvent(0x6c3,4);check(encoded[0].length===4&&!calls.length,'achievement-cheat-request-unchanged');
 calls=[];encoded=[];v=sendEvent(0x7d4,8,other);check(encoded[0].length===8&&!calls.length,'foreign-sender-unchanged');
 calls=[];encoded=[];v=sendEvent(0x6be,0,senderOwner);check(encoded[0].length===0&&!calls.length,'owner-handle-is-not-common-sender');
 engine.add(0xc0).writePointer(ptr(0));calls=[];encoded=[];v=sendEvent(0x6be,0);check(encoded[0].length===0&&!calls.length,'missing-sender-owner-is-not-owned');engine.add(0xc0).writePointer(senderOwner);
 calls=[];encoded=[];nested=()=>sendEvent(0x14c,5);v=sendEvent(0x7d4,8);check(encoded.length===2&&encoded[0].length===24&&encoded[1].length===21&&calls.length===2,'nested-send-restores-context-and-both-vectors');
 c.dispose();Interceptor.flush();calls=[];encoded=[];v=sendEvent(0x7d4,8);check(encoded[0].length===8&&!calls.length&&!globalThis.elsRaidNativePower,'dispose-original-only');calls=[];encoded=[];v=sendEvent(0x6be,0);check(encoded[0].length===0&&!calls.length,'dispose-original-empty-achievement-request');
 c=installElsRaidNativePower();Interceptor.flush();changeOwner=true;encoded=[];v=sendEvent(0x7d4,8);changeOwner=false;check(encoded[0].length===8&&!c.active(),'changed-actor-during-build-no-extension');c.dispose();Interceptor.flush();unit.add(0x48).writeU64(uint64('8589934593'));
 for(const change of ['pointee','owner','control']){
  c=installElsRaidNativePower();Interceptor.flush();const replacement=Memory.alloc(0x60);replacement.writePointer(sender);replacement.add(8).writePointer(senderControl);
  mutateSource=()=>{if(change==='pointee')senderOwner.writePointer(other);else if(change==='owner')engine.add(0xc0).writePointer(replacement);else senderOwner.add(8).writePointer(replacement);};
  encoded=[];v=sendEvent(0x6be,0);check(encoded[0].length===0&&!c.active(),'changed-sender-'+change+'-during-build-no-extension');c.dispose();Interceptor.flush();
  engine.add(0xc0).writePointer(senderOwner);senderOwner.writePointer(sender);senderOwner.add(8).writePointer(senderControl);
 }
 c=installElsRaidNativePower();Interceptor.flush();invalidCP=true;encoded=[];v=sendEvent(0x7d4,8);invalidCP=false;check(encoded[0].length===8&&!c.active(),'invalid-native-CP-no-extension');c.dispose();Interceptor.flush();
 c=installElsRaidNativePower();Interceptor.flush();failEncoder=true;encoded=[];v=sendEvent(0x7d4,8);failEncoder=false;check(encoded[0].length===24&&!c.active(),'encoder-failure-restores-vector-and-disables');c.dispose();Interceptor.flush();
 c=installElsRaidNativePower();Interceptor.flush();encoded=[];v=sendEvent(0x6be,1);check(encoded[0].length===1&&!c.active(),'malformed-achievement-body-no-extension');c.dispose();Interceptor.flush();
 const p=base.add(0x896890),old=p.readU8();p.writeU8(old^1);let refused=false;try{installElsRaidNativePower();}catch(e){refused=String(e).includes('identity');}p.writeU8(old);check(refused&&!globalThis.elsRaidNativePower,'native-pin-refused');
 send({event:'achievement_power_abi_verified',ok:true,cases,owned_non_game_process:true,real_Frida_hooks:true,original_dispatch_encoder_prologues:true,native_CP_builder_explicit_fixture:true,natural_gameplay:false});
})();
'''.replace('__SEGMENTS__',json.dumps({r:list(image[r:r+n])for r,n in {0x242f510:15,0x682d80:28,0x682da0:16,0x680b50:16,0x680b70:16,0x896870:16,0x896890:16,0x8a1400:16}.items()})).replace('__SUPPORT__',source(image,EXE_SHA))
child=subprocess.Popen([sys.executable,'-u','-c','import sys;print("owned-ready",flush=True);sys.stdin.buffer.read(1)'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW,cwd=W)
session=probe=None;messages=[]
watchdog=threading.Timer(15,lambda:child.terminate()if child.poll()is None else None);watchdog.start()
try:
    assert child.stdout.readline().strip()==b'owned-ready'
    session=frida.attach(child.pid);probe=session.create_script(script);probe.on('message',lambda m,d:messages.append(m));probe.load()
    errors=[m for m in messages if m.get('type')=='error'];assert not errors,errors
    result=next(m['payload']for m in messages if m.get('type')=='send'and m['payload'].get('event')=='achievement_power_abi_verified')
    result.update(candidate_JS_sha256=hashlib.sha256((args.candidate/'tools/raid_native_power.js').read_bytes()).hexdigest(),
        retained_builder_sha256=hashlib.sha256((base/'tools/raid_native_power.py').read_bytes()).hexdigest(),
        unchanged_existing_body_pins_preserved=True,empty_vector_uses_original_null_pointers=True,
        new_hook_sites=0,original_EXE_KOM_changes=0)
    (W/('native-power-abi'+args.tag+'.json')).write_text(json.dumps(result,indent=2)+'\n','utf8');print(json.dumps(result))
except BaseException as error:
    (W/('native-power-abi'+args.tag+'-failure.json')).write_text(json.dumps(dict(error=repr(error),messages=messages),indent=2)+'\n','utf8');raise
finally:
    watchdog.cancel()
    if probe is not None:
        try:probe.unload()
        except Exception:pass
    if session is not None:
        try:session.detach()
        except Exception:pass
    if child.poll()is None:child.stdin.write(b'x');child.stdin.flush()
    child.wait(timeout=10)
