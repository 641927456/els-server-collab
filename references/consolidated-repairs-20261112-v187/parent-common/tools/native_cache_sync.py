"""Compose authorized native cache calls into existing verified frame callbacks."""
from pathlib import Path
import hashlib,json
EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
TRACE_TEXT_SHAS=frozenset(('640a6daeffd8e43382a1e0e5de9b3aa4a8a75716f265d7d372f2344179f75bb3',
                           '18f648df8b878a6b7e566a7216c9f187639d7824ad3d1369da0beb3d95149f41',
                           '0b5e92cddf1f2959dfb3ce1fc884756eb1db8514c3aa654bccb5634e16d93b46',
                           '20ba0f2d75c5f1ebb56787755e3b33b1f945f897a6aa0432592dc27062291cce',
                           'a155d2c5b8ab7197340eae32364a48d598ec6b7bffbe5523c443f9f1f0a20a08',
                           '30cbe880fcbf90653140f5125b647c1427a4697c8d47525fc722558255670bc5'))

def compose(snapshot,executable_sha256,template):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:
        raise ValueError('Native power cache client identity')
    if hashlib.sha256(template.replace('\r\n','\n').encode()).hexdigest()not in TRACE_TEXT_SHAS:
        raise ValueError('Native power cache parent trace changed; explicit merge required')
    rvas=(0x896870,0x8a1400,0x8571d0,0xc231e0,0x30d0680,0x89188f,0x117e5ea,0x1c0f996,0x1c27227,0x363ed6f,0x997b00,0x888ca0,0x996270,0x88d6b0,0x87caf0,0x18e8300,0x1bdc220,0x1c143e0,0x7d8b00,0x7d57a0,0x19204f0,0x217e980,0x7ada60,0x18c3290)
    raw=Path(__file__).with_suffix('.js').read_text('utf8')
    rosso=Path(__file__).with_name('rosso_reward_refresh.js').read_text('utf8')
    marker='__ROSSO_REWARD_REFRESH_PINS__'
    if rosso.count(marker)!=1:raise ValueError('Rosso reward refresh source contract')
    sites=(0x234b140,0x22613d1,0xbd9830,0xb7e85b,0x2e63160,0x4ab640,0x4ab6d0)
    rosso=rosso.replace(marker,json.dumps({r:snapshot[r:r+8].hex() for r in sites}))
    raw=rosso+'\n'+raw
    from native_group_wear_sync import source as group_wear_source
    from native_ground_models import source as ground_model_source
    raw=ground_model_source(snapshot,executable_sha256)+'\n'+group_wear_source(snapshot,executable_sha256)+'\n'+raw
    if raw.count('__CACHE_SYNC_PINS__')!=1 or raw.count('__CACHE_SYNC_EXE_SHA__')!=1:raise ValueError('Native cache source contract')
    raw=raw.replace('__CACHE_SYNC_PINS__',json.dumps({r:snapshot[r:r+8].hex()for r in rvas})).replace('__CACHE_SYNC_EXE_SHA__',json.dumps(EXE_SHA))
    if raw.count('__RELATION_SOURCE_PINS__')!=1:raise ValueError('Native relationship source contract')
    relation_pins={0x13a34f0:snapshot[0x13a34f0:0x13a3778].hex(),0x903010:snapshot[0x903010:0x90331d].hex(),0x1382b66:snapshot[0x1382b66:0x1382b6b].hex(),0x1385feb:snapshot[0x1385feb:0x1385ff0].hex(),0x74c470:snapshot[0x74c470:0x74c478].hex(),0x13787e6:snapshot[0x13787e6:0x13787f0].hex()}
    raw=raw.replace('__RELATION_SOURCE_PINS__',json.dumps(relation_pins))
    changes=[
      ("let noahVerifiedSenderReady=false;","let noahVerifiedSenderReady=false;\nlet elsNativeCacheSync=null;"),
      ("  clearInterval(timer);\n  let lastBootstrapState='';","  clearInterval(timer);\n  installElsWearSync();\n  installElsGroundModels();\n  {try{installElsRossoRewardRefresh();}catch(error){note({event:'rosso_reward_panel_refresh_disabled',reason:String(error)});}}\n  {try{installElsRelationSourceSync();}catch(relationError){try{note({event:'native_relation_source_disabled',reason:String(relationError)});}catch(noteError){}}let real=null,failed=false,failure;function ready(){if(real)return real;if(failed)throw failure;try{return real=installElsNativeCacheSync();}catch(error){failed=true;failure=error;try{note({event:'native_cache_sync_disabled',reason:String(error),rollback_errors:installElsNativeCacheSync.failedInstallation?.rollbackErrors||[]});}finally{throw error;}}}elsNativeCacheSync={begin(){ready().begin();},end(){if(real)real.end();},frame(g){ready().frame(g);}};note({event:'native_cache_sync_prepared',initialization:'original-owned-field-or-dungeon-callback'});}\n  if(!enterDungeon){\n   Interceptor.attach(game.base.add(0x30d0660),{onEnter(){elsNativeCacheSync.begin();},onLeave(){elsNativeCacheSync.end();}});\n   Interceptor.attach(game.base.add(0xc231c0),{onEnter(a){this.cacheState=ptr(a[0].toString());},onLeave(){const r=this.cacheState.add(0x908);if(r.readS32()>=0&&r.add(4).readU32()!==0){const g=nativeCall(0x7ada60,'pointer',['pointer'])(r);elsNativeCacheSync.frame(g);}}});\n  }\n  let lastBootstrapState='';"),
      ("    dungeonGame=g;dungeonActor=nativeCall(0x8571d0,'pointer',['pointer'])(g);","    elsNativeCacheSync.frame(g);\n    dungeonGame=g;dungeonActor=nativeCall(0x8571d0,'pointer',['pointer'])(g);"),
      ("   Interceptor.attach(game.base.add(0x30d0660),{\n    onLeave(){","   Interceptor.attach(game.base.add(0x30d0660),{\n    onEnter(){elsNativeCacheSync.begin();},\n    onLeave(){elsNativeCacheSync.end();")]
    result=template
    for before,after in changes:
        if result.count(before)!=1:raise ValueError('Native cache composition anchor')
        result=result.replace(before,after)
    inverse=result
    for before,after in reversed(changes):
        if inverse.count(after)!=1:raise ValueError('Native cache composition inverse')
        inverse=inverse.replace(after,before)
    if inverse!=template:raise ValueError('Native cache composition source inverse')
    from native_wear_sync import source as wear_source
    from world_event_iteration import compose as world_source
    from dungeon_map_markers import compose as map_source
    from pvp_hp_source import compose as pvp_source
    from startup_ui_visibility import compose as startup_compose
    from activity_guide_lifecycle import compose as guide_compose
    from challenge_scroll_open import compose as challenge_compose
    from guild_native_power import compose as guild_compose
    from dungeon_result_stats import compose as result_compose
    from native_title_options import compose as title_compose
    from raid_native_power import compose as raid_compose
    from native_send_serialization import compose as send_compose
    from my_buff_cleanup import compose as my_buff_source
    from enhancement_cap import compose as enhancement_compose
    return enhancement_compose(snapshot,executable_sha256,my_buff_source(snapshot,executable_sha256,send_compose(snapshot,executable_sha256,raid_compose(snapshot,executable_sha256,title_compose(snapshot,result_compose(snapshot,executable_sha256,guild_compose(snapshot,executable_sha256,challenge_compose(snapshot,executable_sha256,guide_compose(snapshot,executable_sha256,startup_compose(snapshot,executable_sha256,pvp_source(snapshot,executable_sha256,map_source(snapshot,executable_sha256,world_source(snapshot,executable_sha256,wear_source(snapshot,executable_sha256)+'\n'+raw+'\n'+result)))))))))))))
