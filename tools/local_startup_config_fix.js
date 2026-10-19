// Recover only the exact witnessed configuration resource, in its output DTO.
// The client's original decryptor, Lua loader and font registration still run.
const scM=Process.getModuleByName('x2_dx11.exe'),scSpec=__STARTUP_CONFIG_SPEC__;
const scHex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
let scAttempts=0,scHook=null;
const scTimer=setInterval(()=>{
 if(++scAttempts>1200){clearInterval(scTimer);send({event:'startup_config_fix_unavailable'});return;}
 if(scHex(scM.base.add(0x362020),8)!=='__RESOURCE_READER_PREFIX__')return;
 clearInterval(scTimer);
 scHook=Interceptor.attach(scM.base.add(0x362020),{
  onEnter(a){this.out=null;const s=a[2],n=s.add(16).readU64().toNumber();if(n!==scSpec.name.length)return;const p=s.add(24).readU64().toNumber()>7?s.readPointer():s;if(p.readUtf16String(n)===scSpec.name)this.out=a[1];},
  onLeave(){
   const p=this.out;if(!p)return;
   if(p.add(0x28).readU32()!==scSpec.size||p.add(0x3c).readU32()!==scSpec.compressed_size||p.add(0x44).readU32()!==scSpec.algorithm||p.add(0x40).readU32()!==scSpec.recorded_key)return;
   const data=p.add(0x30).readPointer();if(data.isNull()||scHex(data,scSpec.compressed_size)!==scSpec.encrypted_hex)return;
   p.add(0x40).writeU32(scSpec.verified_key);
   scHook.detach();scHook=null;
   send({event:'startup_config_key_recovered',name:scSpec.name,old_key:scSpec.recorded_key,key:scSpec.verified_key,encrypted_sha256:scSpec.encrypted_sha256,plaintext_sha256:scSpec.plaintext_sha256,original_loader:true,archive_file_modified:false,observer_removed:true});
  }
 });
 setTimeout(()=>{if(scHook){scHook.detach();scHook=null;send({event:'startup_config_fix_not_matched'});}},30000);
},25);
