"""Compose the approved idol-title native registrations and scoped adapters."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXE_SHA = '6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA = 'c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
SITES = {'aggregate':0x1831280, 'flat':0x2183140, 'update':0x1c18950,
         'cooldown_get':0x1928b70, 'cooldown_set':0x1928bc0, 'effect':0x108f280}
FUNCTIONS = {'valid_game':0x15a0b0, 'resolve_game':0x15a100,
             'actor_model':0x7e9b00, 'model_title':0x98d550,
             'awakening_remaining':0x7d8b40, 'remove_buff':0x1c101a0,
             'vector_assign':0x47f860, 'register_socket':0xa186c0}


def native_pins(snapshot):
    # The signed hidden_fashion observer already validates and attaches to the
    # shared Lua loader's prologue. Verify its untouched body here, retaining
    # that observer and its original-entry check instead of rejecting its patch.
    entries = [*SITES.values(), *FUNCTIONS.values(), 0x3934000, 0xa18590,
               0x11c63a0, 0x7ecd30, 0x36d720, 0x2184ed0, 0x164530,
               0x3936ed0, 0x3937740, 0x3936df0, 0x39363f0]
    return {r: snapshot[r:r+24].hex() for r in entries}


def c_source():
    code = (HERE/'idol_title_runtime.c').read_text('utf8')
    selected = ['99233', '43706', '20305', '200400+index',
                '200410+index*3', '200411+index*3', '200412+index*3']
    names=[f'EffectSet_ELS_Idol_{t}_{phase}' for t in range(38070,38131,10) for phase in ('wear','awaken','skill')]
    return code.replace('__IDOL_SOCKET_COUNT__',str(len(selected))).replace(
        '__IDOL_SOCKET_VALUES__', ''.join(f'selected[{i}]={v};' for i,v in enumerate(selected))).replace(
        '__IDOL_EFFECT_NAMES__',','.join(json.dumps(n) for n in names))


def source(snapshot, executable_sha256):
    if executable_sha256 != EXE_SHA or hashlib.sha256(snapshot).hexdigest() != IMAGE_SHA:
        raise ValueError('Idol title client identity')
    definitions = json.loads((HERE/'idol_title_definitions.json').read_bytes())
    pins = native_pins(snapshot)
    values = {'__IDOL_CODE__':c_source(), '__IDOL_PINS__':pins,
              '__IDOL_SITES__':SITES, '__IDOL_FUNCTIONS__':FUNCTIONS,
              '__IDOL_CHUNK__':list((HERE/'idol_title_definitions.kl').read_bytes()),
              '__IDOL_DEFINITIONS__':definitions}
    raw = (HERE/'idol_titles.js').read_text('utf8')
    for key,value in values.items():
        if raw.count(key)!=1: raise ValueError('Idol title source placeholder '+key)
        raw=raw.replace(key,json.dumps(value,ensure_ascii=True,separators=(',',':')))
    return raw


def compose(snapshot,executable_sha256,template):
    anchor=' installElsGuildNativePower();'
    if template.count(anchor)!=1: raise ValueError('Idol title initialization anchor')
    replacement=' installElsIdolTitles();\n'+anchor
    result=template.replace(anchor,replacement)
    if result.replace(replacement,anchor)!=template: raise ValueError('Idol title composition inverse')
    return source(snapshot,executable_sha256)+'\n'+result
