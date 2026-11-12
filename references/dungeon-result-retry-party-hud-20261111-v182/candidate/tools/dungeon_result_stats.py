"""Compose native PVE report and result-screen reload support."""
from pathlib import Path
import hashlib,json
EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'

def compose(snapshot,executable_sha256,template):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:
        raise ValueError('Dungeon result report client identity')
    anchor=" groupWear=installGroupWear(api);"
    if template.count(anchor)!=1:raise ValueError('Dungeon result report startup anchor')
    guard=" for(const [r,h]of Object.entries(pins))if(bytes(module.base.add(+r))!==h)throw Error('Native power sync identity '+r);"
    if template.count(guard)!=1:raise ValueError('Dungeon result original pin ordering')
    startup='  installElsWearSync();'
    if template.count(startup)!=1:raise ValueError('Hero retry startup anchor')
    script=Path(__file__).with_suffix('.js').read_text(encoding='utf8')
    if script.count('__DUNGEON_RESULT_PINS__')!=1 or script.count('__HERO_RETRY_PINS__')!=1:
        raise ValueError('Dungeon result source contract')
    # The existing trace owns an Interceptor at 682D80 before cache startup.
    # Pin the untouched body +20h of that same function, not its trampoline.
    entries=(0x682da0,0x159670,0x8571d0,0x1ab7ac0,0x1ab6eb0,0xda2f50,
             0x8fe730,0x8f4830,0x8f4c19,0x8f4c2d,0x18ddeb3,0x3b6dbd0,0x3b6dda0,0x3b6dcc0)
    script=script.replace('__DUNGEON_RESULT_PINS__',json.dumps({r:snapshot[r:r+16].hex()for r in entries}))
    script=script.replace('__HERO_RETRY_PINS__',json.dumps(snapshot[0x2d65145:0x2d65168].hex()))
    replacement=anchor+"\n const previousResultStats=globalThis.elsDungeonResultStats;\n dungeonResultStats=installElsDungeonResultStats(()=>mainThread!==0&&Process.getCurrentThreadId()===mainThread);\n ownsDungeonResultStats=previousResultStats!==dungeonResultStats;"
    # Check original bytes before the existing PvP hook changes 1AB7AC0.
    # Preparation has no hook and captures no actor or cache-thread closure.
    template=template.replace(guard,guard+'\n prepareElsDungeonResultStats();')
    template=template.replace(startup,'  installElsHeroRetryFactors(game);\n'
                              "  note({event:'hero_retry_factors_ready'});\n"+startup)
    return script+'\n'+template.replace(anchor,replacement)
