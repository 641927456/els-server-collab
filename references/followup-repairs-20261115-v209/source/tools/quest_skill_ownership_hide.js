// Supplement original quest hiding with ownership already present in native seals.
function installElsQuestSkillOwnershipHide() {
  'use strict';
  if(globalThis.__elsQuestSkillOwnershipHide)return globalThis.__elsQuestSkillOwnershipHide;
  const rules=__RULES__,mod=Process.getModuleByName('x2_dx11.exe');
  const emit=(event,extra={})=>send({event:'quest_skill_ownership_hide_'+event,...extra});
  const address=mod.base.add(rules.function_rva);
  const hex=p=>Array.from(new Uint8Array(p.readByteArray(16)),b=>b.toString(16).padStart(2,'0')).join('');
  if(hex(address)!==rules.prefix16)throw Error('Quest ownership native prefix mismatch');
  const groups=new Map(Object.entries(rules.group_skills).map(([g,ids])=>[Number(g),new Set(ids)]));
  let hook=null,disabled=false,reported=false;
  function owns(unit,group){
    const head=unit.add(0x878).readPointer(),count=unit.add(0x880).readU64().toNumber();
    if(head.isNull()||count>512)throw Error('Quest ownership seal set identity');
    const pending=[head.add(8).readPointer()],seen=new Set(),ids=groups.get(group);let found=false;
    while(pending.length){
      const node=pending.pop();if(node.equals(head)||node.add(25).readU8())continue;
      const identity=node.toString();if(seen.has(identity)||seen.size>=count)throw Error('Quest ownership seal set shape');
      seen.add(identity);if(ids.has(node.add(28).readS32()))found=true;
      pending.push(node.readPointer(),node.add(16).readPointer());
    }
    if(seen.size!==count)throw Error('Quest ownership seal set size');
    return found;
  }
  hook=Interceptor.attach(address,{
    onEnter(args){this.manager=args[0];this.group=rules.quest_groups[String(args[1].toInt32())];},
    onLeave(result){
      if(disabled||!this.group||(result.toUInt32()&255)!==0)return;
      try{
        const engine=mod.base.add(0x4817e70).readPointer();if(engine.isNull())return;
        if(!engine.add(0x88).readPointer().equals(this.manager))return;
        const roster=engine.add(0xc8).readPointer();if(roster.isNull())return;
        const unit=roster.add(0xa0).readPointer();if(unit.isNull()||unit.add(0x48).readU64().compare(0)===0)return;
        if(owns(unit,this.group)){
          result.replace(ptr(1));
          if(!reported){reported=true;emit('applied',{group:this.group});}
        }
      }catch(error){disabled=true;hook.detach();emit('disabled',{reason:String(error)});}
    }
  });
  const support={stop(){disabled=true;if(hook){hook.detach();hook=null;}delete globalThis.__elsQuestSkillOwnershipHide;emit('stopped');}};
  globalThis.__elsQuestSkillOwnershipHide=support;
  emit('ready',{mapped_quests:Object.keys(rules.quest_groups).length,native_predicate_rva:rules.function_rva});
  return support;
}
