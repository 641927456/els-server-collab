// Reuse the existing Frida API fixture, adding the previously missing skip path.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const out=__dirname,priorRoot='G:/els/analysis/dungeon-result-tab-audit-20261106-v1';
const bindings=JSON.parse(fs.readFileSync(path.join(out,'parent-bindings.json'),'utf8')),runtime=bindings.runtime;
const prior=fs.readFileSync(path.join(priorRoot,'verify_hook_cd.cjs'),'utf8');
const split=prior.indexOf('let checks=[]');assert(split>0);
function adapted(sourcePath,full=false){
 let code=full?prior:prior.slice(0,split);
 code=code.replace("path.join(out,'candidate/tools/dungeon_result_stats.js')",JSON.stringify(sourcePath));
 code=code.replace("path.join(out,'candidate/tools/pvp_hp_source.js')",JSON.stringify(path.join(runtime,'tools/pvp_hp_source.js')));
 code=code.replace("path.join(out,'pvp-writer-pins.json')",JSON.stringify(path.join(priorRoot,'pvp-writer-pins.json')));
 // Invalid pointers must fail as they do in Gum, rather than read an invented zero.
 code=code.replace('readU64(){return new U64(',"readU64(){if(this.n<0)throw Error('access violation accessing 0xffffffffffffffff');return new U64(");
 code=code.replace('return{context,events,hooks','return{Ptr,context,events,hooks');
 if(full){
  code=code.replace('assert.equal(count,6);','assert.equal(count,7);');
  code=code.replace("  enter(kind==='discrete'?0x18ddeb3:0x8f4c2d", "  if(kind==='acceleration')enter(0x8f4c19)();\n  enter(kind==='discrete'?0x18ddeb3:0x8f4c2d");
 }
 return code;
}
function factory(sourcePath){
 const box={require,__dirname:out,console,Buffer};vm.createContext(box);
 vm.runInContext(adapted(sourcePath)+'\nglobalThis.makeFixture=fixture;',box);
 return box.makeFixture;
}
function poisonedJoin(f){
 const frame=0x70000000;
 f.mem.set(frame+0x20,1001);f.mem.set(frame+0x28,1);f.mem.set(frame+0x30,-33);
 f.enter(0x8f4c2d,[],{context:{rbp:new f.Ptr(frame)}})();
}
const rows=f=>JSON.parse(JSON.stringify(f.reportRows()));
const old=factory(path.join(runtime,'tools/dungeon_result_stats.js'))();old.context.installElsDungeonResultStats(()=>true);
const leaveOld=old.scope('acceleration');assert.throws(()=>poisonedJoin(old),/access violation/);leaveOld();
const make=factory(path.join(out,'candidate/tools/dungeon_result_stats.js'));
const fixed=make();fixed.context.installElsDungeonResultStats(()=>true);
let leave=fixed.scope('acceleration');
// The three original skip branches all reach this join with no initialized pair.
for(const branch of [0x8f4b63,0x8f4b88,0x8f4bca])assert.doesNotThrow(()=>poisonedJoin(fixed),branch.toString(16));
leave();assert.deepEqual(rows(fixed),{});
leave=fixed.scope('acceleration');fixed.enter(0x8f4c19)();fixed.commit('acceleration',1002,1.5);
// A later skipped iteration must neither read garbage nor reuse the previous delta.
poisonedJoin(fixed);leave();assert.deepEqual(rows(fixed),{'1002':1.5});
leave=fixed.scope('acceleration');fixed.enter(0x8f4c19)();fixed.commit('acceleration',1002,.25);leave();
assert.deepEqual(rows(fixed),{'1002':1.75});
const outer=fixed.scope('acceleration'),remote=fixed.scope('acceleration',false);
fixed.enter(0x8f4c19)();poisonedJoin(fixed);remote();
fixed.enter(0x8f4c19)();fixed.commit('acceleration',1002,.5);outer();
assert.deepEqual(rows(fixed),{'1002':2.25});
leave=fixed.scope('acceleration');fixed.enter(0x8f4c19)();fixed.mem.set(fixed.base+0x478cb88,42);fixed.commit('acceleration',1002,99);
poisonedJoin(fixed);leave();assert.deepEqual(rows(fixed),{});
const checks=['Actual old source reproduces the recorded invalid-pointer error',
 'All three native skip cases ignore uninitialized stack storage',
 'Successful updates followed by skipped iterations count once',
 'Inserted and existing-key deltas continue accumulating',
 'Nested remote trees cannot arm the local recipient',
 'A changed native game generation discards pending old updates'];
const fullBox={require,__dirname:out,console:{log(){}},Buffer};vm.createContext(fullBox);
vm.runInContext(adapted(path.join(out,'candidate/tools/dungeon_result_stats.js'),true),fullBox);
const priorResult=JSON.parse(fs.readFileSync(path.join(out,'hook-verification.json'),'utf8'));
assert(priorResult.passed);
const result={passed:true,checks,existing_lifecycle_checks:priorResult.checks,
 verification:'Frida API fixtures using actual candidate and actual loaded parent sources',game_process:false,natural_battle:false};
fs.writeFileSync(path.join(out,'cooldown-verification.json'),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify({passed:true,new_checks:checks.length,reused_existing_checks:priorResult.checks.length}));
