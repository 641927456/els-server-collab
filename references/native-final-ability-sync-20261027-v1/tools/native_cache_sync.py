"""Compose authorized native cache calls into existing verified frame callbacks."""
from pathlib import Path
import hashlib,json
EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
TRACE_TEXT_SHAS=frozenset(('0b5e92cddf1f2959dfb3ce1fc884756eb1db8514c3aa654bccb5634e16d93b46',
                           '20ba0f2d75c5f1ebb56787755e3b33b1f945f897a6aa0432592dc27062291cce'))

def compose(snapshot,executable_sha256,template):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:
        raise ValueError('Native power cache client identity')
    if hashlib.sha256(template.replace('\r\n','\n').encode()).hexdigest()not in TRACE_TEXT_SHAS:
        raise ValueError('Native power cache parent trace changed; explicit merge required')
    rvas=(0x896870,0x8a1400,0x8571d0,0xc231e0,0x30d0680,0x89188f,0x117e5ea,0x1c0f996,0x1c27227,0x363ed6f,0x997b00,0x888ca0,0x996270,0x88d6b0,0x87caf0,0x18e8300,0x1bdc220,0x1c143e0,0x7d8b00,0x7d57a0,0x19204f0)
    raw=Path(__file__).with_suffix('.js').read_text('utf8')
    if raw.count('__CACHE_SYNC_PINS__')!=1 or raw.count('__CACHE_SYNC_EXE_SHA__')!=1:raise ValueError('Native cache source contract')
    raw=raw.replace('__CACHE_SYNC_PINS__',json.dumps({r:snapshot[r:r+8].hex()for r in rvas})).replace('__CACHE_SYNC_EXE_SHA__',json.dumps(EXE_SHA))
    changes=[
      ("let noahVerifiedSenderReady=false;","let noahVerifiedSenderReady=false;\nlet elsNativeCacheSync=null;"),
      ("  clearInterval(timer);\n  let lastBootstrapState='';","  clearInterval(timer);\n  {let real=null;function ready(){if(real)return real;try{return real=installElsNativeCacheSync();}catch(error){note({event:'native_cache_sync_disabled',reason:String(error)});throw error;}}elsNativeCacheSync={begin(){ready().begin();},end(){if(real)real.end();},frame(g){ready().frame(g);}};note({event:'native_cache_sync_prepared',initialization:'original-owned-field-or-dungeon-callback'});}\n  if(!(enterDungeon&&gateIdentityTest&&populationTest)){\n   Interceptor.attach(game.base.add(0x30d0660),{onEnter(){elsNativeCacheSync.begin();},onLeave(){elsNativeCacheSync.end();}});\n   Interceptor.attach(game.base.add(0xc231c0),{onEnter(a){this.cacheState=ptr(a[0].toString());},onLeave(){const r=this.cacheState.add(0x908);if(r.readS32()>=0&&r.add(4).readU32()!==0){const g=nativeCall(0x7ada60,'pointer',['pointer'])(r);elsNativeCacheSync.frame(g);}}});\n  }\n  let lastBootstrapState='';"),
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
    return raw+'\n'+result
