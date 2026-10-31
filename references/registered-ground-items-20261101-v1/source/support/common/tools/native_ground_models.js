// Model-name argument only, exclusively the verified native ground caller.
function installElsGroundModels() {
 'use strict';
 if(globalThis.elsGroundModels)return globalThis.elsGroundModels;
 const m=Process.getModuleByName('x2_dx11.exe'),pins=__GROUND_MODEL_PINS__,aliases=__GROUND_MODEL_ALIASES__;
 const emit=(event,fields={})=>send({event:'native_ground_models_'+event,timestamp:Date.now(),...fields});
 const hex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),x=>x.toString(16).padStart(2,'0')).join('');
 for(const[r,h]of Object.entries(pins))if(hex(m.base.add(+r),h.length/2)!==h)throw Error('Ground models native pin '+r);
 const names=new Map();
 const namePointer=name=>{if(!names.has(name))names.set(name,Memory.allocUtf16String(name));return names.get(name);};
 const bodies={8:'Upbody',9:'Lowbody',10:'Hand',11:'Foot'};
 let hook=null,disabled=false,applied=0;
 function fail(error){disabled=true;if(hook)hook.detach();emit('guard_rejected',{error:String(error)});}
 hook=Interceptor.attach(m.base.add(0x97a980),{
  onEnter(args){
   if(disabled||!this.returnAddress.equals(m.base.add(0x1032390)))return;
   try{
    const object=this.context.r14,definition=object.add(0x88).readPointer(),pool=m.base.add(0x478ae30).readPointer();
    if(definition.isNull()||pool.isNull())throw Error('Ground definition/pool unavailable');
    const off=definition.add(0x9c).readU32(),length=off?pool.add(off).readU16():0;
    if(length>512)throw Error('Ground model string bound');
    const original=length?pool.add(off+2).readUtf16String(length):'',input=args[3].readUtf16String();
    if(input!==original)throw Error('Ground model argument/definition mismatch');
    let replacement=aliases[original];
    if(original===''){
     const type=(definition.add(8).readU32()>>>3)&31,part=bodies[definition.add(213).readU8()];
     if(type===1)replacement='DropItemDrop_Weapon_Common';
     else if(type===2){
      if(part)replacement='DropItemDrop_'+part+'_Common';
      else if(definition.add(213).readU8()===6)replacement='DropItemPouch'; // Native hair items use the pouch category.
      else throw Error('Blank armor model position');
     }
     else replacement='DropItemPouch';
    }
    if(replacement===undefined)return;
    this.correction={template:definition.readU32(),original,replacement};this.output=args[1];
    args[3]=namePointer(replacement);
   }catch(error){fail(error);}
  },
  onLeave(){if(!this.correction||disabled)return;try{
   if(this.output.readPointer().isNull())throw Error('Replacement native model is null');
   applied++;emit('applied',this.correction);
  }catch(error){fail(error);}}
 });
 globalThis.elsGroundModels={get applied(){return applied;},get disabled(){return disabled;}};
 emit('installed',{caller_RVA:'1032390',native_loader_RVA:'97A980',disk_resources_modified:false});
 return globalThis.elsGroundModels;
}
