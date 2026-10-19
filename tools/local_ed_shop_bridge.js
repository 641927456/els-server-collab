// Isolated local-ED profile adapter. All game/UI mutations use original methods.
// D79 cannot carry product+56 (ED); delegate its catalog action to native 80D.
const ebM=Process.getModuleByName('x2_dx11.exe'),ebPrefixes=__ED_BRIDGE_PREFIXES__;
const ebHex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
for(const [r,h] of Object.entries(ebPrefixes))if(ebHex(ebM.base.add(Number(r)),8)!==h)throw Error('Local ED bridge prefix '+r);
const ebNative=(r,ret,args)=>new NativeFunction(ebM.base.add(r),ret,args,{exceptions:'propagate'});
let ebCashRequest=null;
const ebEdRequest=ebNative(0x313a340,'void',['pointer']);
const ebCategory=ebNative(0x1c4e7a0,'void',['pointer','int','int','int']);
const ebCart=ebNative(0x1c71230,'void',['pointer']);
const ebCopyInts=ebNative(0x47bb40,'pointer',['pointer','pointer']);
const ebMoveInts=ebNative(0x47a770,'pointer',['pointer','pointer']);
const ebRoleData=__ED_ROLE_DATA__,ebClassTypes=__ED_CLASS_TYPES__;
function ebCurrentRole(){
 const g=ebM.base.add(0x4817e70).readPointer().add(0xc8).readPointer();
 if(!ebLocalPlayer(g))throw Error('Shop character unavailable');
 const type=ebClassTypes[g.add(0xa0).readPointer().add(0x58).readU16()];
 if(!ebRoleData[type])throw Error('Unknown shop character type');return type;
}
function ebInitializeHome(){
 const type=ebCurrentRole(),ebHomeLists=ebRoleData[type].home;
 const items=ebM.base.add(0x4817e70).readPointer().add(0x58).readPointer();
 for(let k=0;k<3;k++){
  const ids=ebHomeLists[k],raw=Memory.alloc(Math.max(4,ids.length*4)),view=Memory.alloc(24),owned=Memory.alloc(24);
  ids.forEach((id,i)=>raw.add(i*4).writeU32(id));view.writePointer(raw);view.add(8).writePointer(raw.add(ids.length*4));view.add(16).writePointer(raw.add(ids.length*4));
  // Copy allocates with the game's allocator; move transfers ownership.
  // Never store Frida-managed backing memory in a game-owned vector.
  ebCopyInts(owned,view);ebMoveInts(items.add(0xf0+k*24),owned);
 }
 send({event:'local_ed_shop_home_initialized',timestamp:Date.now(),unit_type:type,counts:ebHomeLists.map(x=>x.length)});
}
let ebFrame=null,ebTimer=null,ebPending=null,ebCatalog=__ED_ALREADY_LOADED__,ebCatalogType=null;
// Enter Scaleform from a completed town frame, after the menu/input callback
// has unwound. The original toggle still performs every UI/state mutation.
let ebToggleOriginal=null,ebTogglePending=null,ebToggleFrame=null,ebToggleTimer=null;
function ebStopToggle(){if(ebToggleFrame){ebToggleFrame.detach();ebToggleFrame=null;}if(ebToggleTimer){clearTimeout(ebToggleTimer);ebToggleTimer=null;}ebTogglePending=null;}
function ebStopFrame(){if(ebFrame){ebFrame.detach();ebFrame=null;}if(ebTimer){clearTimeout(ebTimer);ebTimer=null;}ebPending=null;}
function ebOwnedUi(ui){return !ui.isNull()&&ui.readPointer().equals(ebM.base.add(0x4242a38));}
function ebLocalPlayer(game){
 if(game.isNull())return false;const player=game.add(0xa0).readPointer();if(player.isNull())return false;
 // The local roster allocates 1001..1016, with a fixed 16-character limit.
 const uid=player.add(0x48).readU64();return uid.compare(1001)>=0&&uid.compare(1016)<=0;
}
function ebOwnedState(s){
 if(s.isNull()||!s.readPointer().add(0x188).readPointer().equals(ebM.base.add(0x311c030))||!ebOwnedUi(s.add(0x440).readPointer()))return false;
 const manager=ebM.base.add(0x4817e70).readPointer(),g=manager.add(0xc8).readPointer();
 return ebLocalPlayer(g);
}
const ebToggleReplacement=new NativeCallback(s=>{
 if(!ebOwnedState(s)){ebToggleOriginal(s);return;}
 if(ebTogglePending){send({event:'local_ed_shop_toggle_coalesced',timestamp:Date.now()});return;}
 const queued={state:s,at:Date.now()};ebTogglePending=queued;
 ebToggleFrame=Interceptor.attach(ebM.base.add(0x30d0660),{onEnter(a){this.state=a[0];},onLeave(){
  if(ebTogglePending!==queued||!this.state.equals(queued.state)||Date.now()-queued.at<32)return;
  if(!ebOwnedState(queued.state)){ebStopToggle();send({event:'local_ed_shop_toggle_cancelled',reason:'state changed'});return;}
  ebStopToggle();
  const ui=queued.state.add(0x440).readPointer(),type=ebCurrentRole();
  if(ui.add(0x128).readU8()===0&&ebCatalogType!==type){
   // The original shop toggle uses this same destructor when its catalog
   // version changes. Clear while closed so a new role cannot reuse old SKUs.
   ebNative(0x69ca00,'void',['pointer'])(ebM.base.add(0x4817e70).readPointer().add(0x58).readPointer());
   ebCatalog=false;
   send({event:'local_ed_shop_role_cache_cleared',timestamp:Date.now(),previous_type:ebCatalogType,unit_type:type});
  }
  send({event:'local_ed_shop_deferred_toggle_started',timestamp:Date.now(),state:queued.state.toString()});
  ebToggleOriginal(queued.state);
  send({event:'local_ed_shop_deferred_toggle_returned',timestamp:Date.now()});
 }});
 ebToggleTimer=setTimeout(()=>{if(ebTogglePending===queued){ebStopToggle();send({event:'local_ed_shop_toggle_cancelled',reason:'town frame unavailable'});}},5000);
 send({event:'local_ed_shop_toggle_queued',timestamp:queued.at,state:s.toString(),delay_ms:32});
},'void',['pointer']);
const ebToggleTrampoline=Interceptor.replaceFast(ebM.base.add(0x311c030),ebToggleReplacement);
ebToggleOriginal=new NativeFunction(ebToggleTrampoline,'void',['pointer'],{exceptions:'propagate'});
function ebQueue(ui){
 if(!ebOwnedUi(ui))return;
 ebPending=ui;if(ebFrame)return;
 ebFrame=Interceptor.attach(ebM.base.add(0x30d0660),{onLeave(){
  try{
   const target=ebPending;if(!target||!ebOwnedUi(target))return;
   if(target.add(0x128).readU8()!==1)return;
   if(target.add(0x500).readU8()!==1)return;
   const movie=target.add(0x490).readPointer();if(movie.isNull()||movie.add(0x10).readPointer().isNull())return;
   ebStopFrame();
   if(ebCatalog){
    // 80E populates the shared native product map and keeps each product's ED
    // flag. Real resource category IDs allow normal home/category/page events
    // to rebuild their own lists, instead of forcing the hidden ED-only tab.
    ebInitializeHome();ebCategory(target,0,0,0);
   }
   ebCart(target);
   send({event:'local_ed_shop_ui_ready',timestamp:Date.now(),category:target.add(0x130).readS32(),subcategory:target.add(0x134).readS32(),cart_count:target.add(0x3c0).readPointer().sub(target.add(0x3b8).readPointer()).toInt32()/4,frame_observer_removed:true});
  }catch(e){ebStopFrame();send({event:'local_ed_shop_bridge_error',error:String(e)});}
 }});
 ebTimer=setTimeout(()=>{ebStopFrame();send({event:'local_ed_shop_ui_timeout'});},30000);
}
const ebReplacement=new NativeCallback((s,mode)=>{
 send({event:'local_ed_shop_catalog_action',timestamp:Date.now(),state:s.toString(),mode});
 try{
  const manager=ebM.base.add(0x4817e70).readPointer(),game=manager.add(0xc8).readPointer();
  if(mode===0&&!s.isNull()&&s.readPointer().add(0x188).readPointer().equals(ebM.base.add(0x311c030))&&
     ebLocalPlayer(game)&&
     s.add(0x578).readS32()===0&&s.add(0x4b4).readS32()===1&&ebOwnedUi(s.add(0x440).readPointer())){
   send({event:'local_ed_shop_catalog_routed',timestamp:Date.now(),method:'313A340',mode});
   ebEdRequest(s);return;
  }
 }catch(e){send({event:'local_ed_shop_bridge_error',error:String(e)});}
 ebCashRequest(s,mode);
},'void',['pointer','int']);
// replaceFast makes nested native entry replay take the same delegate as a
// normal game call; its returned trampoline is the explicit fallback path.
const ebOriginal=Interceptor.replaceFast(ebM.base.add(0x31133f0),ebReplacement);
ebCashRequest=new NativeFunction(ebOriginal,'void',['pointer','int'],{exceptions:'propagate'});
Interceptor.attach(ebM.base.add(0x313a890),{onEnter(a){this.s=a[0];this.b=a[4];},onLeave(){
 const consumed=this.b.add(32).readU32();
 const type=ebCurrentRole(),expected=ebRoleData[type].size;
 ebCatalog=consumed===expected;
 if(ebCatalog)ebCatalogType=type;
 if(ebCatalog)ebQueue(this.s.add(0x440).readPointer());
 send({event:'local_ed_shop_catalog_applied',timestamp:Date.now(),unit_type:type,consumed,expected_size:expected,expected_catalog:ebCatalog});
}});
Interceptor.attach(ebM.base.add(0x1c45370),{onEnter(a){this.ui=a[0];this.show=a[1].toUInt32()&255;},onLeave(){
 if(this.show===1)ebQueue(this.ui);else if(ebPending&&ebPending.equals(this.ui))ebStopFrame();
}});
Interceptor.attach(ebM.base.add(0x1c4d500),{onEnter(a){this.ui=a[0];this.b=a[4];},onLeave(){
 if(!ebOwnedUi(this.ui))return;
 send({event:'local_ed_shop_cart_ack',timestamp:Date.now(),consumed:this.b.add(32).readU32(),ready:this.ui.add(0x500).readU8()});
 if(this.ui.add(0x500).readU8()!==1)ebQueue(this.ui);
}});
Interceptor.attach(ebM.base.add(0x23d6a80),{onEnter(a){this.ui=a[0];this.b=a[4];},onLeave(){
 if(!ebOwnedUi(this.ui))return;
 send({event:'local_ed_shop_deposit_ack',timestamp:Date.now(),consumed:this.b.add(32).readU32(),ready:this.ui.add(0x500).readU8(),page:this.ui.add(0x30c).readS32(),items_bytes:this.ui.add(0x1d8).readPointer().sub(this.ui.add(0x1d0).readPointer()).toInt32()});
}});
send({event:'local_ed_shop_bridge_ready',timestamp:Date.now(),deferred_native_entry:true,no_os_input:true});
