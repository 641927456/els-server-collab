 function refreshDue(unit,selected,channel,actor=null,force=false){
  // Reuse the native weak Game generation already used by group wear. The
  // temporary lastDungeon field alternates during Field callbacks, so it is
  // not a scene lifetime. Store scheduling metadata only, never native outputs.
  const epoch=identity+':'+bytes(module.base.add(0x478cb88));
  if(epoch!==refreshEpoch){refreshRecords.clear();refreshEpoch=epoch;}
  const key=unit.toString(),binding=selected.uid+':'+selected.klass+':'+selected.family+':'+unit.add(0x29c0).readPointer();
  let row=refreshRecords.get(key);
  if(!row||row.binding!==binding){row={binding,powerAt:null,abilityAt:null,actorAbilityAt:null,actor:null,side:null};refreshRecords.set(key,row);}
  const nativeSide=unit.add(0x2f54).readS32(),side=nativeSide+':'+(nativeSide===2?unit.add(0x2f50).readU8():'');
  if(side!==row.side){row.side=side;row.powerAt=null;row.abilityAt=null;row.actorAbilityAt=null;}
  // A projection without an Actor must not erase the Actor binding, otherwise
  // UserInfo/Actor callbacks would alternate keys and defeat the interval.
  if(actor&&row.actor!==actor.toString()){row.actor=actor.toString();row.actorAbilityAt=null;}
  const now=Date.now(),previous=row[channel];
  if(!force&&previous!==null&&now>=previous&&now-previous<refreshIntervalMs){
   if(channel==='powerAt')powerSkipped++;else abilitySkipped++;return false;
  }
  row[channel]=now;return true;
 }
 function sevenAt(){throw Error("Baseline boundary marker");}
 function abilityInputs(unit,selected,actor,reason,strict=false,provided=null,immediate=false){
  if(disabled||abilityBusy||nativeBuildDepth||Process.getCurrentThreadId()!==mainThread||!describe(unit,selected))return;
  // Periodic entry points share this Unit's budget. Full UserInfo projection
  // must finish before native cloning/Actor initialization; owner reports are
  // also fresh. Supplied peer snapshots are applied without recomputing them.
  // A Unit projection cannot postpone Actor application: repeated immediate
  // projections would otherwise keep that different consumer from ever running.
  if(!provided&&!refreshDue(unit,selected,actor?'actorAbilityAt':'abilityAt',actor,strict||immediate))return;
  if(!provided&&(strict||immediate))immediateAbilityCalculations++;
  abilityBusy=true;const started=Date.now(),outside=!busy;
  try{
   const naked=sevenAt(unit.add(0x220)),first=provided?provided.first:completeAbility(unit,0),second=provided?provided.second:(selected.family===10?completeAbility(unit,1):first);
   if(!sameSeven(sevenAt(unit.add(0x268)),first.values)||!sameSeven(sevenAt(unit.add(0x2b0)),second.values)){
    supplyFinalInputs(unit.add(0x48),first.input,second.input);finalInputWrites++;
    if(!sameSeven(sevenAt(unit.add(0x268)),first.values)||!sameSeven(sevenAt(unit.add(0x2b0)),second.values))throw Error('Original final ability consumer mismatch');
    emit('ability_inputs_written',{uid:selected.uid,unit:unit.toString(),family:selected.family,klass:selected.klass,reason,sides:[first.values,second.values],original_producer:'888CA0',original_consumer:'88D6B0',health_setter_calls:0});
   }
   if(actor){
    if(!actor.readPointer().add(0x4f8).readPointer().equals(module.base.add(0x18e8300)))throw Error('Unqualified original Actor ability virtual');
    let side=unit.add(0x2f54).readS32();if(side===2)side=unit.add(0x2f50).readU8()===1?1:0;if(side!==0&&side!==1)throw Error('Original Actor ability side');
    const value=side===1?second:first;
    if(!sameSeven(sevenAt(actor.add(0x1698)),value.values)){
     const beforeHealth={current:currentHP(actor),maximum:maximumHP(actor)};
     supplyActorBase(actor,value.input);actorBaseWrites++;
     // Original full attribute receiver BAA6F0 refreshes native dirty components
     // then limits current HP through Actor virtual2F0 only when HP exceeds max.
     // Match that sequence; raising max HP never invokes a current-HP setter.
     refreshActor(actor);const maximum=maximumHP(actor),current=currentHP(actor);let clamped=false;
     if(!Number.isFinite(maximum)||maximum<=0||!Number.isFinite(current))throw Error('Original refreshed health range');
     if(current>maximum){if(!actor.readPointer().add(0x2f0).readPointer().equals(module.base.add(0x19204f0)))throw Error('Unqualified original HP clamp virtual');clampCurrentHP(actor,maximum);healthClamps++;clamped=true;}
     const afterHealth={current:currentHP(actor),maximum:maximumHP(actor)};
     if(afterHealth.current>afterHealth.maximum||afterHealth.current>beforeHealth.current)throw Error('Original health clamp/preservation mismatch');
     if(!sameSeven(sevenAt(actor.add(0x1698)),value.values))throw Error('Original Actor base ability mismatch');
     emit('ability_actor_base_written',{uid:selected.uid,unit:unit.toString(),actor:actor.toString(),family:selected.family,klass:selected.klass,reason,side,seven:value.values,original_consumer:'18E8300',original_refresh:'1C143E0',original_full_refresh_reference:'BAA6F0/BAA949..BAA9BF',health_before:beforeHealth,health_after:afterHealth,original_current_HP_clamp:clamped,health_setter_calls:clamped?1:0});
    }
   }
   if(!sameSeven(sevenAt(unit.add(0x220)),naked))throw Error('Original naked input changed during final ability supply');
  }catch(error){if(strict)throw error;disabled=true;emit('disabled',{reason:String(error),writes,final_input_writes:finalInputWrites,actor_base_writes:actorBaseWrites,original_HP_clamps:healthClamps});}
  finally{const elapsed=Date.now()-started;abilityCalculations++;abilityMs+=elapsed;if(outside)abilityOutsideCacheMs+=elapsed;abilityBusy=false;}
 }

 let busy=null;
