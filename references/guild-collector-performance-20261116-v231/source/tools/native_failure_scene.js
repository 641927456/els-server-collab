// Failure-only, bounded reads. These are observations, not allocation history.
function elsEvidenceRead(out,key,read){
 try{out[key]=read();}catch(error){(out.read_errors??=[]).push({field:key,error:String(error).slice(0,160)});}
}
function elsEvidenceRegion(address){
 const p=ptr(address),r=Process.findRangeByAddress(p);
 return r?{address:p.toString(),base:r.base.toString(),size:r.size,protection:r.protection}:{address:p.toString(),mapped:false};
}
function elsFaultScene(out,knownBuild){
 const scene={schema:1,stage:'saved_context_read_at_crash_filter',atomic:false,regions:[],fields:{}};
 const access=(out.code==='0xc0000005'||out.code==='0xc0000006')?out.parameters[1]:undefined;
 const roles=[['instruction',out.address],['access',access],...['rcx','rax','r8','r13','rsp'].map(k=>[k,out.registers[k]])];
 for(const [role,address]of roles){if(address===undefined)continue;elsEvidenceRead(scene,role,()=>{scene.regions.push({role,...elsEvidenceRegion(address)});return address;});}
 const m=Process.findModuleByAddress(ptr(out.address));
 if(!m){scene.site_status='module_unavailable';return scene;}
 scene.module={name:m.name,base:m.base.toString(),size:m.size,rva:ptr(out.address).sub(m.base).toString()};
 if(!knownBuild||m.name.toLowerCase()!=='x2_dx11.exe'){scene.site_status='generic_only';return scene;}
 const rva=ptr(out.address).sub(m.base).toUInt32();
 const pins={0x1c5ec35:'8b4118',0x8f872b:'3310',0x3b738e4:'41884002'};
 if(!(rva in pins)){scene.site_status='generic_only';return scene;}
 const expected=pins[rva];let actual;
 elsEvidenceRead(scene,'instruction_pin',()=>actual=Array.from(new Uint8Array(ptr(out.address).readByteArray(expected.length/2)),v=>v.toString(16).padStart(2,'0')).join(''));
 if(actual!==expected){scene.site_status='instruction_pin_mismatch';return scene;}
 scene.site_status='pinned_site';const f=scene.fields;
 if(rva===0x1c5ec35){
  const member=ptr(out.registers.rcx);f.member=member.toString();
  elsEvidenceRead(f,'member_first_pointer',()=>member.readPointer().toString());
  elsEvidenceRead(f,'member_value_18',()=>member.add(0x18).readS32());
  elsEvidenceRead(f,'member_value_1c',()=>member.add(0x1c).readS32());
 }else if(rva===0x8f872b){
  elsEvidenceRead(f,'operand_u32',()=>ptr(out.registers.rax).readU32());
  f.record_base=out.registers.r13;f.operand=out.registers.rax;
 }else{
  elsEvidenceRead(f,'output_write_region',()=>elsEvidenceRegion(ptr(out.registers.r8).add(2)));
  elsEvidenceRead(f,'stream',()=>ptr(out.registers.rsp).add(0x80).readPointer().toString());
  if(f.stream){const stream=ptr(f.stream);
   elsEvidenceRead(f,'input_pointer',()=>stream.readPointer().toString());
   elsEvidenceRead(f,'available_input',()=>stream.add(8).readU32());
   elsEvidenceRead(f,'output_pointer',()=>stream.add(0x10).readPointer().toString());
   elsEvidenceRead(f,'available_output',()=>stream.add(0x18).readU32());
   for(const key of ['input_pointer','output_pointer'])if(f[key])elsEvidenceRead(f,key+'_region',()=>elsEvidenceRegion(f[key]));
  }
 }
 return scene;
}
function elsStackCandidates(bytes){
 const result=[];
 for(let offset=0;offset+8<=bytes.length&&result.length<12;offset+=8){
  const address=ptr('0x'+bytes.slice(offset,offset+8).reverse().map(v=>v.toString(16).padStart(2,'0')).join(''));
  const module=Process.findModuleByAddress(address);if(!module)continue;
  const region=Process.findRangeByAddress(address);if(!region||!region.protection.includes('x'))continue;
  result.push({stack_offset:offset,module:module.name,rva:address.sub(module.base).toString()});
 }
 return {unwound:false,candidates_not_frames:true,items:result};
}
function elsGuardError(message,facts){const error=Error(message);error.guardFacts=facts;return error;}
function elsGuardScene(manager,id,row,action,error,imageBase){
 const scene={schema:1,stage:'after_guard_rejection',atomic:false,template:id,operation:action?'action_book':'align_cap',manager:manager.toString(),row:row.toString(),check:String(error).slice(0,200),facts:error.guardFacts||{},fields:{}};
 const f=scene.fields;
 elsEvidenceRead(f,'manager_region',()=>elsEvidenceRegion(manager));
 elsEvidenceRead(f,'row_region',()=>elsEvidenceRegion(row));
 elsEvidenceRead(f,'begin',()=>manager.add(0x30).readPointer().toString());
 elsEvidenceRead(f,'end',()=>manager.add(0x38).readPointer().toString());
 if(f.begin){const begin=ptr(f.begin);
  elsEvidenceRead(f,'table_magic',()=>begin.readU32());
  elsEvidenceRead(f,'table_version',()=>begin.add(4).readU32());
  elsEvidenceRead(f,'count',()=>begin.add(8).readU32());
  if(f.end)f.span=ptr(f.end).sub(begin).toString();
  if(Number.isInteger(f.count)&&f.count>0&&f.count<=250000&&!row.isNull()){
   const offset=Number(row.sub(begin.add(16+f.count*4)).toString());f.row_offset=offset;
   if(Number.isSafeInteger(offset)&&offset>=0&&offset%232===0&&offset<f.count*232)
    elsEvidenceRead(f,'key_template',()=>begin.add(16+offset/232*4).readU32());
  }
 }
 if(!row.isNull()){
  elsEvidenceRead(f,'row_template',()=>row.readU32());
  elsEvidenceRead(f,'cap',()=>row.add(16).readS32());
 }
 if(action){
  elsEvidenceRead(f,'strings',()=>imageBase.add(0x478ae30).readPointer().toString());
  if(f.strings){const strings=ptr(f.strings);
   elsEvidenceRead(f,'strings_region',()=>elsEvidenceRegion(strings));
   elsEvidenceRead(f,'strings_magic',()=>strings.readU32());
   elsEvidenceRead(f,'strings_count',()=>strings.add(8).readU32());
   elsEvidenceRead(f,'marker_length',()=>strings.add(78383346).readU16());
   elsEvidenceRead(f,'marker_name',()=>strings.add(78383348).readUtf16String(15));
  }
 }
 return scene;
}
