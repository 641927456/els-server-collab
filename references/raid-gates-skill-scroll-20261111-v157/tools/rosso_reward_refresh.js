// Original Rosso reward redraw after the successful ticket ACK and weekly state write.
function installElsRossoRewardRefresh() {
 const pins=__ROSSO_REWARD_REFRESH_PINS__;
 const base=game.base;
 for (const [rva,expected] of Object.entries(pins)) {
  const actual=Array.from(new Uint8Array(base.add(Number(rva)).readByteArray(expected.length/2)),v=>v.toString(16).padStart(2,'0')).join('');
  if(actual!==expected)throw Error('Rosso reward refresh client identity: '+rva);
 }
 const call=(r,result,args)=>new NativeFunction(base.add(r),result,args);
 const valid=call(0x4ab640,'uint8',['pointer']);
 const resolve=call(0x4ab6d0,'pointer',['pointer']);
 const refresh=call(0x2e63160,'void',['pointer','int']);
 const pending=new Map();
 const readHandle=h=>valid(h)?resolve(h):ptr(0);
 function current(){
  const app=base.add(0x4817e80).readPointer(),engine=base.add(0x4817e70).readPointer();
  if(app.isNull()||engine.isNull()||app.add(0x160).readS32()!==14)return null;
  const chars=engine.add(0xc8).readPointer(),menu=engine.add(0x558).readPointer();
  if(chars.isNull()||menu.isNull())return null;
  const actor=chars.add(0xa0).readPointer(),map=menu.add(0x320).readPointer();
  if(actor.isNull()||map.isNull())return null;
  const wrapper=map.add(0x48).readPointer();
  if(wrapper.isNull()||!wrapper.readPointer().equals(base.add(0x42cf428)))return null;
  const handle=wrapper.add(8),panel=readHandle(handle);
  if(panel.isNull()||!panel.readPointer().equals(base.add(0x42cf460))||panel.add(0x58).readS32()!==1)return null;
  const root=readHandle(panel.add(0x68));if(root.isNull())return null;
  const shown=root.readPointer().add(0x3a0).readPointer();
  if(shown.compare(base)<0||shown.compare(base.add(0x3ae4000))>=0||!new NativeFunction(shown,'uint8',['pointer'])(root))return null;
  const mode=panel.add(0x5c).readS32();if(mode!==1&&mode!==2)return null;
  return {key:[actor.add(0x48).readU64(),handle.readPointer(),panel.add(0x68).readPointer(),mode].join(':'),panel,mode};
 }
 const useListener=Interceptor.attach(base.add(0x234b140),{onEnter(args){
  if(this.returnAddress.equals(base.add(0x22613d6)))this.dto=args[1];
 },onLeave(){
  if(this.dto===undefined)return;
  const tid=this.threadId;pending.delete(tid);
  if(this.dto.readS32()!==0||this.dto.add(28).readS32()!==135909)return;
  const selected=current();if(selected===null)return;
  pending.set(tid,{key:selected.key,at:Date.now()});
 }});
 try { Interceptor.attach(base.add(0xbd9830),{onEnter(args){
  if(!this.returnAddress.equals(base.add(0xb7e860)))return;
  const mark=pending.get(this.threadId);if(mark===undefined)return;
  pending.delete(this.threadId);
  if(Date.now()-mark.at>5000)return;
  const buffer=args[4],begin=buffer.add(8).readPointer(),end=buffer.add(16).readPointer();
  if(end.sub(begin).toInt32()!==69)return;
  const header=new DataView(begin.readByteArray(69));
  if(header.getInt32(0)!==1||header.getUint32(28)!==9||header.getUint8(68)!==0)return;
  this.bound=mark;this.buffer=buffer;
 },onLeave(result){
  if(this.bound===undefined||(result.toUInt32()&255)!==1||this.buffer.add(32).readU32()!==69)return;
  const selected=current();if(selected===null||selected.key!==this.bound.key)return;
  refresh(selected.panel,selected.mode);
  note({event:'rosso_reward_panel_refreshed',mode:selected.mode});
 }}); } catch (error) { useListener.detach(); throw error; }
 note({event:'rosso_reward_panel_refresh_ready'});
}
