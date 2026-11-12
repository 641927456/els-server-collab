// Apply the signed castle table changes at the native script buffer boundary.
(function installShadowCastle(){
 'use strict';
 const module=Process.getModuleByName('x2_dx11.exe');
 const {loader,pins,resources}=__SHADOW_CASTLE_CONTRACT__;
 const entry=module.base.add(loader);
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
 if(!Object.entries(pins).every(([rva,value])=>hex(module.base.add(Number(rva)),value.length/2)===value))
  throw Error('Shadow Castle native Lua buffer entry does not match');

 const bySize=new Map();
 for(const row of resources){
  let group=bySize.get(row.size);
  if(group===undefined){group=new Map();bySize.set(row.size,group);}
  group.set(row.sha256,row);
 }

 Interceptor.attach(entry,{
  onEnter(args){
   const size=args[2].toUInt32(), group=bySize.get(size);
   if(group===undefined || !args[2].equals(ptr(size)) || args[1].isNull() || args[1].readU32()!==0x824c4b1b)return;
   const original=args[1].readByteArray(size);
   const row=group.get(Checksum.compute('sha256',original));
   if(row===undefined)return;

   const input=new Uint8Array(original);
   const length=size+row.edits.reduce((n,[offset,count,value])=>n+value.length/2-count,0);
   const output=new Uint8Array(length);
   let consumed=0, written=0;
   for(const [offset,count,value] of row.edits){
    output.set(input.subarray(consumed,offset),written);
    written+=offset-consumed;
    for(let i=0;i<value.length;i+=2)output[written++]=parseInt(value.slice(i,i+2),16);
    consumed=offset+count;
   }
   output.set(input.subarray(consumed),written);
   if(Checksum.compute('sha256',output.buffer)!==row.updated_sha256)
    throw Error('Shadow Castle Lua transform does not match '+row.name);
   this.buffer=Memory.alloc(length);
   this.buffer.writeByteArray(output.buffer);
   this.resource=row.name;
   args[1]=this.buffer;
   args[2]=ptr(length);
  },
  onLeave(result){
   if(this.resource===undefined)return;
   if((result.toInt32()&255)!==1)throw Error('Shadow Castle native Lua rejected '+this.resource);
   send({event:'shadow_castle_native_resource_loaded',resource:this.resource,
         caller:this.returnAddress.sub(module.base).toString()});
  }
 });
 send({event:'shadow_castle_native_support_ready',resource_count:resources.length});
})();
