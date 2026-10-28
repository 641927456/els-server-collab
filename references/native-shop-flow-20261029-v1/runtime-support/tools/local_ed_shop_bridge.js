// Retained ED adapter plus one guarded duplicate-UI instruction site.
// Original native methods own every UI mutation.
const ebM=Process.getModuleByName('x2_dx11.exe'),ebPrefixes=__ED_BRIDGE_PREFIXES__;
const ebHex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
for(const [r,h]of Object.entries(ebPrefixes))if(ebHex(ebM.base.add(Number(r)),h.length/2)!==h)throw Error('Local ED bridge prefix '+r);
const ebNative=(r,ret,args)=>new NativeFunction(ebM.base.add(r),ret,args,{exceptions:'propagate'});
let ebCashRequest=null,ebToggleOriginal=null;
const ebEdRequest=ebNative(0x313a340,'void',['pointer']);
const ebCategory=ebNative(0x1c4e7a0,'void',['pointer','int','int','int']);
const ebCart=ebNative(0x1c71230,'void',['pointer']);
const ebCopyInts=ebNative(0x47bb40,'pointer',['pointer','pointer']);
const ebMoveInts=ebNative(0x47a770,'pointer',['pointer','pointer']);
const ebRoleData=__ED_ROLE_DATA__,ebClassTypes=__ED_CLASS_TYPES__;
const ebNativeData=__ED_NATIVE_DATA__,ebCategories=new Set(ebNativeData.categories);
const ebInitiallyLoaded=__ED_ALREADY_LOADED__;
const ebCatalogLimit=20000,ebByteLimit=5+28*ebCatalogLimit;
const ebLoads=new Map();

// SHA256 identifies the complete bounded native80E body for lifecycle/audit.
// It is not a fixed-release acceptance gate; legal server catalogue changes
// use original native resources and exact native-map semantics below.
function ebSha256(buffer){
 const input=new Uint8Array(buffer),n=input.length;
 if(n>ebByteLimit)throw Error('Shop digest bound');
 const size=(n+9+63)&~63,data=new Uint8Array(size);data.set(input);data[n]=0x80;
 const view=new DataView(data.buffer);view.setUint32(size-8,Math.floor(n/0x20000000));view.setUint32(size-4,(n*8)>>>0);
 const k=[0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
 const h=[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19],w=new Uint32Array(64),rot=(x,b)=>(x>>>b)|(x<<(32-b));
 for(let offset=0;offset<size;offset+=64){
  for(let j=0;j<16;j++)w[j]=view.getUint32(offset+j*4);
  for(let j=16;j<64;j++){const a=w[j-15],b=w[j-2];w[j]=(w[j-16]+(rot(a,7)^rot(a,18)^(a>>>3))+w[j-7]+(rot(b,17)^rot(b,19)^(b>>>10)))>>>0;}
  let[a,b,c,d,e,f,g,t]=h;
  for(let j=0;j<64;j++){const q=(t+(rot(e,6)^rot(e,11)^rot(e,25))+((e&f)^(~e&g))+k[j]+w[j])>>>0;
   const z=((rot(a,2)^rot(a,13)^rot(a,22))+((a&b)^(a&c)^(b&c)))>>>0;
   t=g;g=f;f=e;e=(d+q)>>>0;d=c;c=b;b=a;a=(q+z)>>>0;
  }
  for(const[j,value]of[a,b,c,d,e,f,g,t].entries())h[j]=(h[j]+value)>>>0;
 }
 return h.map(v=>v.toString(16).padStart(8,'0')).join('');
}

function ebOwnedUi(ui){return !ui.isNull()&&ui.readPointer().equals(ebM.base.add(0x4242a38));}
function ebLocalPlayer(game){
 if(game.isNull())return false;const player=game.add(0xa0).readPointer();if(player.isNull())return false;
 const manager=ebM.base.add(0x4817e70).readPointer();
 if(manager.isNull()||!manager.add(0xc8).readPointer().equals(game))return false;
 const uid=player.add(0x48).readU64();return uid.compare(1001)>=0&&uid.compare('9223372036854775807')<0;
}
function ebOwnedState(s){
 if(s.isNull()||!s.readPointer().add(0x188).readPointer().equals(ebM.base.add(0x311c030))||!ebOwnedUi(s.add(0x440).readPointer()))return false;
 return ebLocalPlayer(ebM.base.add(0x4817e70).readPointer().add(0xc8).readPointer());
}
function ebIdentity(state){
 if(!ebOwnedState(state))throw Error('Shop state unavailable');
 const manager=ebM.base.add(0x4817e70).readPointer(),game=manager.add(0xc8).readPointer(),player=game.add(0xa0).readPointer();
 const type=ebClassTypes[player.add(0x58).readU16()],ui=state.add(0x440).readPointer();
 if(!ebRoleData[type])throw Error('Unknown shop character type');
 const uid=player.add(0x48).readU64().toString();
 return{state,manager,game,player,ui,type,uid,key:[state,manager,game,player,ui,type,uid].join(':')};
}
function ebCurrentRole(){return ebContext?ebIdentity(ebContext.state).type:null;}
let ebGeneration=0,ebContext=null,ebClosedOwner=null,ebCatalog=false,ebCatalogType=null;
let ebFrame=null,ebTimer=null,ebPending=null,ebTogglePending=null,ebToggleFrame=null,ebToggleTimer=null;
function ebStopToggle(){if(ebToggleFrame){ebToggleFrame.detach();ebToggleFrame=null;}if(ebToggleTimer){clearTimeout(ebToggleTimer);ebToggleTimer=null;}ebTogglePending=null;}
function ebStopFrame(){if(ebFrame){ebFrame.detach();ebFrame=null;}if(ebTimer){clearTimeout(ebTimer);ebTimer=null;}ebPending=null;}
function ebCurrent(ctx){
 if(!ctx||ebContext!==ctx||ctx.generation!==ebGeneration)return false;
 try{return ebIdentity(ctx.state).key===ctx.key;}catch(e){return false;}
}
function ebRetiredClosed(state){
 const retired=ebClosedOwner;if(!retired||ebContext||!retired.state.equals(state))return null;
 try{const current=ebIdentity(state);return current.key===retired.key&&current.ui.add(0x128).readU8()===0?retired:null;}catch(e){return null;}
}
function ebAbandon(reason){
 // Keep at most one exact owned closed identity until the next owned action.
 // An already in-flight catalogue must not reopen that cancelled UI. This is
 // not authority over other roles/states or an unobserved original UI entry.
 const prior=ebContext;
 if(ebCurrent(prior))try{if(prior.ui.add(0x128).readU8()===0)ebClosedOwner={state:prior.state,key:prior.key,generation:prior.generation,closedReason:reason};}catch(e){}
 ebStopFrame();ebStopToggle();ebGeneration++;ebContext=null;ebCatalog=false;ebCatalogType=null;
 send({event:'local_ed_shop_generation_cancelled',timestamp:Date.now(),reason});
}

function ebReadCatalogue(buffer){
 const start=buffer.add(32).readU32(),begin=buffer.add(8).readPointer(),end=buffer.add(16).readPointer();
 const total=end.sub(begin).toInt32(),length=total-start;
 if(begin.isNull()||total<0||start>total||length<5||length>ebByteLimit)throw Error('Shop body buffer bound');
 const raw=begin.add(start).readByteArray(length),view=new DataView(raw),count=view.getUint32(1);
 if(view.getUint8(0)!==1||count>ebCatalogLimit||length!==5+28*count)throw Error('Shop complete native body shape');
 const groups=new Map(),seen=new Set();
 for(let n=0;n<count;n++){
  const offset=5+28*n,sku=view.getUint32(offset),template=view.getInt32(offset+4),category=view.getInt32(offset+8),price=view.getInt32(offset+12),quantity=view.getInt32(offset+20);
  if(!sku||sku>=0x80000000||template<=0||category<0||price<0||quantity<1||quantity>65535||view.getInt32(offset+16)!==0||view.getInt32(offset+24)!==0||seen.has(sku))throw Error('Shop canonical product row');
  seen.add(sku);if(!groups.has(template))groups.set(template,[]);groups.get(template).push({sku,template,category,price,quantity});
 }
 return{start,length,count,sha256:ebSha256(raw),groups};
}
function ebKnownTemplate(template){
 const ranges=ebNativeData.item_ranges;let low=0,high=ranges.length;
 while(low<high){const middle=(low+high)>>>1,pair=ranges[middle];
  if(template<pair[0])high=middle;else if(template>pair[1])low=middle+1;else return true;
 }
 return false;
}
function ebQualifyCatalogue(ctx,body){
 for(const[template,rows]of body.groups){
  if(!ebKnownTemplate(template))throw Error('Shop template absent from original client resources');
  const mask=ebNativeData.role_masks[template];
  if(mask!==undefined&&(mask&(1<<(ctx.type-1)))===0)throw Error('Shop established role-specific template differs');
  for(const row of rows)if(!ebCategories.has(row.category))throw Error('Shop category absent from original client resources');
 }
 const profile=ebRoleData[ctx.type],known=profile.find(p=>p.size===body.length&&p.count===body.count&&p.sha256===body.sha256);
 // Home data is featured placement only. Removed offers are filtered out;
 // new valid offers remain reachable through the original category browser.
 return{size:body.length,count:body.count,sha256:body.sha256,known_profile:!!known,
  home:(known||profile[0]).home.map(group=>group.filter(id=>body.groups.has(id)))};
}
function ebNativeCatalogue(ctx,catalogue){
 // Same original product map/row layout already used by the retained exact-
 // build quantity selector. Verify every expected native row, not only a hash.
 const manager=ctx.manager.add(0x58).readPointer();if(manager.isNull())throw Error('Shop product manager unavailable');
 const head=manager.add(0xc8).readPointer();if(head.isNull())throw Error('Shop product map unavailable');
 const count=manager.add(0xd0).readU64();
 if(count.compare(catalogue.groups.size)!==0)throw Error('Shop native template count differs');
 const todo=[head.add(8).readPointer()],seen=new Set();let total=0;
 while(todo.length){
  const node=todo.pop();if(node.isNull())throw Error('Shop native tree null child');
  if(node.equals(head)){if(node.add(0x19).readU8()!==1)throw Error('Shop native sentinel');continue;}
  if(node.add(0x19).readU8()!==0||seen.has(node.toString())||seen.size>=ebCatalogLimit)throw Error('Shop native tree bound/cycle');
  seen.add(node.toString());const template=node.add(0x20).readS32(),expected=catalogue.groups.get(template),product=node.add(0x28).readPointer();
  if(!expected||product.isNull())throw Error('Shop native extra/missing template');
  const begin=product.add(0x10).readPointer(),end=product.add(0x18).readPointer();
  if(begin.isNull()||!end.equals(begin.add(expected.length*0x57)))throw Error('Shop native pack vector differs');
  const bySku=new Map(expected.map(row=>[row.sku,row])),packs=new Set();
  for(let i=0;i<expected.length;i++){
   const row=begin.add(i*0x57),sku=row.readU32(),e=bySku.get(sku);
   if(!e||packs.has(sku)||row.add(4).readU32()!==e.template||row.add(0x28).readS32()!==e.category||row.add(0x2c).readS32()!==e.price||row.add(0x31).readU16()!==e.quantity||row.add(0x56).readU8()!==1)throw Error('Shop native SKU/category/ED/quantity differs');
   packs.add(sku);total++;
  }
  todo.push(node.readPointer(),node.add(0x10).readPointer());
 }
 if(seen.size!==catalogue.groups.size||total!==catalogue.count)throw Error('Shop native total template/SKU coverage differs');
 return true;
}
function ebInitializeHome(ctx){
 const home=ctx.catalogue.home,items=ctx.manager.add(0x58).readPointer();
 for(let k=0;k<3;k++){
  if(!ebCurrent(ctx))throw Error('Shop home generation changed');
  const ids=home[k];if(ids.some(id=>!ctx.products.has(id)))throw Error('Shop home contains absent product');
  const raw=Memory.alloc(Math.max(4,ids.length*4)),view=Memory.alloc(24),owned=Memory.alloc(24);
  ids.forEach((id,i)=>raw.add(i*4).writeU32(id));view.writePointer(raw);view.add(8).writePointer(raw.add(ids.length*4));view.add(16).writePointer(raw.add(ids.length*4));
  ebCopyInts(owned,view);ebMoveInts(items.add(0xf0+k*24),owned);
 }
 send({event:'local_ed_shop_home_initialized',timestamp:Date.now(),unit_type:ctx.type,generation:ctx.generation,counts:home.map(v=>v.length)});
}
function ebRecover(ctx,reason){
 if(!ebCurrent(ctx)||ctx.failed)return;
 ctx.failed=true;ebStopFrame();ebCatalog=false;ebCatalogType=null;
 send({event:'local_ed_shop_recovery_requested',timestamp:Date.now(),generation:ctx.generation,reason});
 // Close only through the retained native toggle, on its existing town-frame
 // site. No flag writes, synthetic input or automatic reopen is introduced.
 if(ctx.ui.add(0x128).readU8()===1)ebScheduleToggle(ctx.state,true);
 else ebAbandon(reason);
}
function ebRetryClosed(ctx,reason){
 if(!ebCurrent(ctx)||ctx.ui.add(0x128).readU8()!==0||(ctx.retryCount||0)>=1)return false;
 ctx.retryCount=(ctx.retryCount||0)+1;ctx.catalogue=null;ctx.products=null;ctx.initialized=false;ebCatalog=false;ebCatalogType=null;
 // An old-role reply may already have merged into the original map. Clear
 // only while this shop is still closed, as in original version invalidation,
 // then issue one ordinary read request; economic requests are never replayed.
 ebNative(0x69ca00,'void',['pointer'])(ctx.manager.add(0x58).readPointer());
 ctx.requested=true;ebEdRequest(ctx.state);ebQueue(ctx.ui);
 send({event:'local_ed_shop_closed_catalogue_retry',timestamp:Date.now(),generation:ctx.generation,reason,retries:ctx.retryCount});return true;
}
function ebQueue(ui){
 const ctx=ebContext;if(!ebCurrent(ctx)||ctx.failed||ctx.recovery||!ctx.ui.equals(ui)||ctx.initialized)return;
 if(ebPending===ctx)return;ebStopFrame();ebPending=ctx;
 ebFrame=Interceptor.attach(ebM.base.add(0x30d0660),{onEnter(a){this.state=a[0];},onLeave(){
  if(!ebPending||ebPending!==ctx)return;
  try{
   if(!ebCurrent(ctx)||!this.state.equals(ctx.state)){ebAbandon('frame context changed');return;}
   const target=ctx.ui;
   if(target.add(0x128).readU8()!==1)return;
   if(!ebCatalog||!ctx.catalogue||target.add(0x500).readU8()!==1)return;
   const movie=target.add(0x490).readPointer();if(movie.isNull()||movie.add(0x10).readPointer().isNull())return;
   ebStopFrame();ctx.initialized=true;
   ebInitializeHome(ctx);if(!ebCurrent(ctx))return;
   ebCategory(target,0,0,0);if(!ebCurrent(ctx))return;
   ebCart(target);if(!ebCurrent(ctx))return;
   if(target.add(0x128).readU8()!==1||target.add(0x500).readU8()!==1)throw Error('Shop readiness changed during native initialization');
   send({event:'local_ed_shop_ui_ready',timestamp:Date.now(),generation:ctx.generation,category:target.add(0x130).readS32(),subcategory:target.add(0x134).readS32(),frame_observer_removed:true,catalog_sha256:ctx.catalogue.sha256});
   if(ctx.closeRequested)ebScheduleToggle(ctx.state,true);
  }catch(e){ebRecover(ctx,String(e));}
 }});
 ebTimer=setTimeout(()=>{if(ebPending===ctx){send({event:'local_ed_shop_ui_timeout',generation:ctx.generation});if(ebCurrent(ctx))ebRecover(ctx,'native UI/catalogue timeout');else ebAbandon('catalogue timeout after context changed');}},30000);
}
function ebScheduleToggle(s,recovery=false){
 if(!ebOwnedState(s)){if(!recovery)ebToggleOriginal(s);return;}
 const identity=ebIdentity(s),opening=identity.ui.add(0x128).readU8()===0;
 if(recovery&&opening){ebAbandon('recovery already closed');return;}
 const active=ebContext;
 if(!recovery&&ebCurrent(active)&&active.key===identity.key&&active.opening&&!active.failed&&!active.initialized){
  if(!opening)active.closeRequested=true;
  send({event:'local_ed_shop_opening_action_coalesced',timestamp:Date.now(),generation:active.generation,close_requested:!!active.closeRequested});return;
 }
 if(ebTogglePending&&ebTogglePending.key===identity.key&&ebTogglePending.opening===opening){send({event:'local_ed_shop_toggle_coalesced',timestamp:Date.now()});return;}
 ebStopFrame();ebStopToggle();
 ebClosedOwner=null;
 const queued={...identity,generation:++ebGeneration,at:Date.now(),opening,recovery,initialized:false,failed:false,catalogue:null,products:null,requested:false};
 ebContext=queued;ebCatalog=false;ebCatalogType=null;ebTogglePending=queued;
 ebToggleFrame=Interceptor.attach(ebM.base.add(0x30d0660),{onEnter(a){this.state=a[0];},onLeave(){
  if(ebTogglePending!==queued||!this.state.equals(queued.state)||Date.now()-queued.at<32)return;
  try{
   if(!ebCurrent(queued)||queued.ui.add(0x128).readU8()!==(queued.opening?0:1)){ebAbandon('toggle context changed');return;}
   // Original311C030 refuses a close until the native UI-ready producer has
   // completed. Wait, without inventing readiness or claiming recovery.
   if(!queued.opening&&queued.ui.add(0x500).readU8()!==1)return;
   ebStopToggle();
   if(queued.opening){
    // The original toggle uses this destructor when its catalogue changes.
    // Always refresh a closed entry, including return from a dungeon, rather
    // than reuse an old map/role verdict across an unobserved scene lifetime.
    ebNative(0x69ca00,'void',['pointer'])(queued.manager.add(0x58).readPointer());
    send({event:'local_ed_shop_role_cache_cleared',timestamp:Date.now(),unit_type:queued.type,generation:queued.generation});
   }
   send({event:'local_ed_shop_deferred_toggle_started',timestamp:Date.now(),generation:queued.generation,recovery:queued.recovery});
   ebToggleOriginal(queued.state);
   send({event:'local_ed_shop_deferred_toggle_returned',timestamp:Date.now(),generation:queued.generation});
   if(!queued.opening&&ebOwnedUi(queued.ui)&&queued.ui.add(0x128).readU8()===0)send({event:'local_ed_shop_native_close_completed',timestamp:Date.now(),generation:queued.generation,recovery:queued.recovery});
   if(queued.opening&&ebCurrent(queued))ebQueue(queued.ui);
  }catch(e){ebRecover(queued,String(e));}
 }});
 ebToggleTimer=setTimeout(()=>{if(ebTogglePending===queued){const current=ebCurrent(queued);let ready=null;if(current)try{ready=queued.ui.add(0x500).readU8()===1;}catch(e){}send({event:'local_ed_shop_recovery_unavailable',generation:queued.generation,native_ready:ready,current_context:current});ebAbandon('town frame/native close readiness unavailable');}},5000);
 send({event:'local_ed_shop_toggle_queued',timestamp:queued.at,generation:queued.generation,recovery,delay_ms:32});
}
const ebToggleReplacement=new NativeCallback(s=>ebScheduleToggle(s),'void',['pointer']);
const ebToggleTrampoline=Interceptor.replaceFast(ebM.base.add(0x311c030),ebToggleReplacement);
ebToggleOriginal=new NativeFunction(ebToggleTrampoline,'void',['pointer'],{exceptions:'propagate'});
const ebReplacement=new NativeCallback((s,mode)=>{
 send({event:'local_ed_shop_catalog_action',timestamp:Date.now(),state:s.toString(),mode});
 try{
  if(mode===0&&ebOwnedState(s)&&s.add(0x578).readS32()===0&&s.add(0x4b4).readS32()===1){
   const ctx=ebContext;
   if(!ebCurrent(ctx)||ctx.recovery||ctx.failed||!ctx.state.equals(s))return;
   if(ctx.requested){send({event:'local_ed_shop_catalog_request_coalesced',generation:ctx.generation});return;}
   ctx.requested=true;send({event:'local_ed_shop_catalog_routed',timestamp:Date.now(),method:'313A340',mode,generation:ctx.generation});ebEdRequest(s);return;
  }
 }catch(e){if(ebContext)ebRecover(ebContext,String(e));return;}
 ebCashRequest(s,mode);
},'void',['pointer','int']);
const ebOriginal=Interceptor.replaceFast(ebM.base.add(0x31133f0),ebReplacement);
ebCashRequest=new NativeFunction(ebOriginal,'void',['pointer','int'],{exceptions:'propagate'});
Interceptor.attach(ebM.base.add(0x313a890),{onEnter(a){
 this.s=a[0];this.b=a[4];this.ctx=ebContext;this.closedOwner=ebRetiredClosed(this.s);this.catalogue=null;this.error=null;
 this.entryOwned=ebCurrent(this.ctx)&&this.ctx.state.equals(this.s);this.reentrySkipped=false;this.uiBlocked=false;this.retryStarted=false;
 let stack=ebLoads.get(this.threadId);if(!stack){stack=[];ebLoads.set(this.threadId,stack);}stack.push(this);
 try{this.catalogue=ebReadCatalogue(this.b);}catch(e){this.error=String(e);}
},onLeave(){
 const stack=ebLoads.get(this.threadId);if(stack){const index=stack.lastIndexOf(this);if(index>=0)stack.splice(index,1);if(!stack.length)ebLoads.delete(this.threadId);}
 if(this.uiBlocked){
  send({event:'local_ed_shop_catalog_rejected',timestamp:Date.now(),generation:this.ctx?this.ctx.generation:null,reason:this.error||'stale catalogue UI blocked',native_UI_reentry_blocked:true,retry_started:this.retryStarted});
  if(!this.retryStarted&&ebCurrent(ebContext))ebRecover(ebContext,this.error||'stale catalogue UI blocked');
  return;
 }
 if(this.closedSkipped){send({event:'local_ed_shop_closed_late_catalogue_suppressed',timestamp:Date.now(),generation:this.closedOwner.generation});return;}
 if(this.closePendingSkipped){send({event:'local_ed_shop_closing_late_catalogue_suppressed',timestamp:Date.now(),generation:this.ctx.generation});return;}
 const ctx=this.ctx;
 if(!ebCurrent(ctx)||!ctx.state.equals(this.s)||ctx.recovery||ctx.failed){
  // The original handler runs before onLeave. A rejected old-generation
  // callback can already have merged products: never keep a current verdict
  // unless its complete native map still matches that current source.
  const active=ebContext;
  if(ebCurrent(active)&&active.catalogue)try{ebNativeCatalogue(active,{groups:active.products,count:active.catalogue.count});}catch(e){ebRecover(active,'stale catalogue mutated native products');}
  return;
 }
 try{
  if(this.error)throw Error(this.error);
  const body=this.catalogue,consumed=this.b.add(32).readU32()-body.start;
  if(consumed!==body.length)throw Error('Shop original decoder did not consume complete body');
  const accepted=ebQualifyCatalogue(ctx,body);
  ebNativeCatalogue(ctx,body);
  const duplicate=ctx.catalogue!==null;
  ctx.catalogue=accepted;ctx.products=body.groups;if(!this.reentrySkipped)ctx.initialized=false;ebCatalog=true;ebCatalogType=ctx.type;ebQueue(ctx.ui);
  send({event:'local_ed_shop_catalog_applied',timestamp:Date.now(),unit_type:ctx.type,generation:ctx.generation,consumed,count:body.count,catalog_sha256:body.sha256,expected_catalog:true,known_profile:accepted.known_profile,native_products_match:true,duplicate,native_duplicate_ui_reentry_skipped:this.reentrySkipped});
 }catch(e){send({event:'local_ed_shop_catalog_rejected',timestamp:Date.now(),generation:ctx.generation,reason:String(e)});ebRecover(ctx,String(e));}
}});
// The original mode0 branch repeats menu cleanup and1C45370(show1), including
// ready-flag clearing, for a duplicate catalogue. Keep original parsing/wait/
// map work, but do not restart the same current UI lifecycle a second time.
// At the original mode test, change only CPU ECX0 to2 for a qualified skip;
// original test/cmp/jne takes its own cleanup. State+578 and PC stay intact.
Interceptor.attach(ebM.base.add(0x313abce),function(){
 const stack=ebLoads.get(this.threadId),load=stack&&stack[stack.length-1];
 if(!load||stack.length>4||this.context.rcx.toInt32()!==0||!this.context.rsi.equals(load.s))return;
 if(load.closedOwner){
  if(ebRetiredClosed(load.s)===load.closedOwner){load.closedSkipped=true;this.context.rcx=ptr(2);}
  return;
 }
 if(!load.entryOwned)return;
 const ctx=load.ctx;
 try{
  if(ebCurrent(ctx)&&ctx.state.equals(load.s)&&ctx.opening===false){load.closePendingSkipped=true;this.context.rcx=ptr(2);return;}
  if(!ebCurrent(ctx)||ctx.failed||ctx.recovery||!ctx.state.equals(load.s))throw Error('Stale owned catalogue generation');
  if(load.error||!load.catalogue)throw Error(load.error||'Missing complete catalogue source');
  ebQualifyCatalogue(ctx,load.catalogue);ebNativeCatalogue(ctx,load.catalogue);
  if(load.b.add(32).readU32()-load.catalogue.start!==load.catalogue.length)throw Error('Incomplete original catalogue consumption');
  if(ctx.catalogue&&ctx.catalogue.sha256===load.catalogue.sha256){
   load.reentrySkipped=true;this.context.rcx=ptr(2);
   send({event:'local_ed_shop_duplicate_native_ui_preserved',timestamp:Date.now(),generation:ctx.generation,initialized:ctx.initialized,catalog_sha256:ctx.catalogue.sha256});
  }
 }catch(e){
  // Ownership was established at the original handler entry. Reject only its
  // local UI restart, preserving original read/wait/map work and exit cleanup.
  load.uiBlocked=true;load.error=String(e);this.context.rcx=ptr(2);
  const active=ebContext;
  try{if(ebCurrent(active)&&active.state.equals(load.s))load.retryStarted=ebRetryClosed(active,load.error);}catch(retryError){load.error+='; '+String(retryError);}
  send({event:'local_ed_shop_native_ui_reentry_blocked',timestamp:Date.now(),reason:load.error,retry_started:load.retryStarted});
 }
});
Interceptor.attach(ebM.base.add(0x1c45370),{onEnter(a){this.ui=a[0];this.show=a[1].toUInt32()&255;this.ctx=ebContext;},onLeave(){
 const ctx=this.ctx;if(!ebCurrent(ctx)||!ctx.ui.equals(this.ui))return;
 if(this.show===1)ebQueue(this.ui);else ebAbandon('native shop closed');
}});
Interceptor.attach(ebM.base.add(0x1c4d500),{onEnter(a){this.ui=a[0];this.b=a[4];this.ctx=ebContext;},onLeave(){
 if(!ebCurrent(this.ctx)||!this.ctx.ui.equals(this.ui))return;
 send({event:'local_ed_shop_cart_ack',timestamp:Date.now(),consumed:this.b.add(32).readU32(),ready:this.ui.add(0x500).readU8(),generation:this.ctx.generation});
 if(this.ui.add(0x500).readU8()!==1)ebQueue(this.ui);
}});
Interceptor.attach(ebM.base.add(0x23d6a80),{onEnter(a){this.ui=a[0];this.b=a[4];this.ctx=ebContext;},onLeave(){
 if(!ebCurrent(this.ctx)||!this.ctx.ui.equals(this.ui))return;
 send({event:'local_ed_shop_deposit_ack',timestamp:Date.now(),consumed:this.b.add(32).readU32(),ready:this.ui.add(0x500).readU8(),page:this.ui.add(0x30c).readS32(),generation:this.ctx.generation});
 if(this.ui.add(0x500).readU8()!==1)ebQueue(this.ui);
}});
send({event:'local_ed_shop_bridge_ready',timestamp:Date.now(),deferred_native_entry:true,no_os_input:true,complete_catalogue_identity:true,preloaded_catalogue_requires_fresh_entry:ebInitiallyLoaded});
