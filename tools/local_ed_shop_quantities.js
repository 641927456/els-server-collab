// Exact-build ED pack selection. The native ED setters otherwise force index 0.
// Keep their fallback and use the original update method for verified packs only.
(function () {
 if(globalThis.ownedShopQuantitySelectors)throw Error('Shop quantity selectors already installed');
 const m=ebM,prefixes=__SHOP_QUANTITY_PREFIXES__,sizes=[1,10,50,100];
 for(const [r,h] of Object.entries(prefixes)){
  const actual=Array.from(new Uint8Array(m.base.add(+r).readByteArray(h.length/2)),v=>v.toString(16).padStart(2,'0')).join('');
  if(actual!==h)throw Error('Shop quantity build guard '+r);
 }
 const native=(r,ret,args)=>new NativeFunction(m.base.add(r),ret,args,{exceptions:'propagate'});
 const update=native(0x1c85fa0,'uint64',['pointer','int','int']);
 const displayed=native(0x1c87a50,'pointer',['pointer','int']);
 function verified(ui,template,index){
  if(!Number.isInteger(template)||template<=0||template>=0x80000000||!Number.isInteger(index)||index<0||index>=sizes.length||!ebOwnedUi(ui))return false;
  const app=m.base.add(0x4817e70).readPointer();if(app.isNull())return false;
  const manager=app.add(0x58).readPointer();if(manager.isNull())return false;
  const head=manager.add(0xc8).readPointer();if(head.isNull())return false;
  let node=head.add(8).readPointer(),product=null;
  for(let depth=0;depth<64;depth++){
   if(node.isNull()||node.add(0x19).readU8()!==0)break;
   const key=node.add(0x20).readS32();
   if(key===template){product=node.add(0x28).readPointer();break;}
   node=node.add(key<template?0x10:0).readPointer();
  }
  if(!product||product.isNull())return false;
  const begin=product.add(0x10).readPointer(),end=product.add(0x18).readPointer();
  if(begin.isNull()||!end.equals(begin.add(4*0x57)))return false;
  const price=begin.add(0x2c).readS32(),category=begin.add(0x28).readS32(),unitSku=begin.readU32();
  if(price<=0||!Number.isSafeInteger(price*100)||price*100>=0x80000000||unitSku===0||unitSku>=0x80000000)return false;
  for(let i=0;i<sizes.length;i++){
   const row=begin.add(i*0x57),sku=row.readU32();
   if(row.add(4).readU32()!==template||row.add(0x56).readU8()!==1||row.add(0x31).readU16()!==sizes[i]||
      row.add(0x28).readS32()!==category||row.add(0x2c).readS32()!==price*sizes[i]||
      sku!==(i===0?unitSku:1500000000+4*template+i))return false;
  }
  return true;
 }
 const originalTemplate=native(0x1c90060,'uint64',['pointer','int','int']);
 const originalRow=native(0x1c90010,'uint64',['pointer','int','int']);
 const byTemplate=new NativeCallback((ui,template,index)=>{
  let accepted=false;try{accepted=verified(ui,template,index);}catch(e){}
  if(accepted)return update(ui,template,index);
  return originalTemplate(ui,template,index);
 },'uint64',['pointer','int','int']);
 const byRow=new NativeCallback((ui,row,index)=>{
  let template=0,accepted=false;
  try{
   if((row===0||row===1)&&ebOwnedUi(ui)){
    const item=displayed(ui,row);
    if(!item.isNull()){
     template=item.readS32();
     accepted=verified(ui,template,index);
    }
   }
  }catch(e){}
  if(accepted)return update(ui,template,index);
  return originalRow(ui,row,index);
 },'uint64',['pointer','int','int']);
 const selectors={callbacks:[byTemplate,byRow],originals:[originalTemplate,originalRow]},installed=[];
 try{
  // Ordinary replace supports this exact prologue; replaceFast cannot relocate it.
  Interceptor.replace(m.base.add(0x1c90060),byTemplate);installed.push(m.base.add(0x1c90060));
  Interceptor.replace(m.base.add(0x1c90010),byRow);installed.push(m.base.add(0x1c90010));
  Interceptor.flush();
  globalThis.ownedShopQuantitySelectors=selectors;
  send({event:'local_ed_shop_quantity_selection_ready',sizes,original_update:'1C85FA0',verified_catalog_only:true});
 }catch(error){
  if(globalThis.ownedShopQuantitySelectors===selectors)delete globalThis.ownedShopQuantitySelectors;
  let cleanupError=null;
  for(const target of installed.reverse())try{Interceptor.revert(target);}catch(e){cleanupError=e;}
  try{Interceptor.flush();}catch(e){cleanupError=e;}
  if(cleanupError)throw Error('Shop quantity cleanup failed: '+cleanupError+'; setup: '+error);
  throw error;
 }
})();
