// Fill only the native return input for the current server-confirmed visit.
function installElsFestivalReturnOrigin(){
 'use strict';
 const m=Process.getModuleByName('x2_dx11.exe'),pins=__FESTIVAL_ORIGIN_PINS__;
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),x=>x.toString(16).padStart(2,'0')).join('');
 for(const [r,h]of Object.entries(pins))if(hex(m.base.add(+r),h.length/2)!==h)throw Error('Festival return native identity '+r);
 const towns=new Set(__FESTIVAL_ORIGIN_TOWNS__);
 const address=m.base.add(0xb7c170),types=['pointer','uint64','uint32','uint64','pointer'];
 const original=new NativeFunction(address,'uint8',types,{exceptions:'propagate'});
 const replacement=new NativeCallback((self,a,b,kind,buffer)=>{
  if(kind.toString()!=='32766')return original(self,a,b,kind,buffer);
  const begin=buffer.add(8).readPointer(),end=buffer.add(16).readPointer(),offset=buffer.add(32).readU32();
  if(begin.isNull()||end.compare(begin)<0)return 1;
  const size=end.sub(begin).toInt32();
  if(size<0||size>65500||offset>size||size-offset!==13)return 1;
  const p=begin.add(offset);buffer.add(32).writeU32(size);
  if(p.readU8()!==1)return 1;
  const uid=uint64('0x'+hex(p.add(1),8)),town=p.add(9).readU32();
  // The wire is big endian; NativePointer scalar reads use host order.
  const source=((town>>>24)|((town>>>8)&0xff00)|((town<<8)&0xff0000)|(town<<24))>>>0;
  if(!towns.has(source))return 1;
  const engine=m.base.add(0x4817e70).readPointer();if(engine.isNull())return 1;
  const manager=engine.add(0xc8).readPointer(),stage=engine.add(0x490).readPointer();
  if(manager.isNull()||stage.isNull()||stage.add(0x68).readS32()!==1503)return 1;
  const unit=manager.add(0xa0).readPointer();if(unit.isNull()||unit.add(0x48).readU64().compare(uid)!==0)return 1;
  stage.add(0xb8).writeS32(source);
  send({event:'festival_return_origin_applied',uid:uid.toString(),town:source});
  return 1;
 },'uint8',types);
 Interceptor.replace(address,replacement);
 // Retain the callback for this Script lifetime. There is no per-visit cache.
 return replacement;
}
