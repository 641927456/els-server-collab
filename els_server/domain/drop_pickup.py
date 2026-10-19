"""The 20 original D0 serializer modes for this verified DX11 build.

Field order and XORs come from the restored native writer's success paths.
Modes 0/2/4 also match original semantic DTOs and real network requests.
This decoder grants nothing; the server validates issued identity/ownership.
"""
from els_server.paths import PROJECT_ROOT
import functools
import hashlib
import json
import math
import struct
from pathlib import Path

BODY_SHA='9b463001d7b99fc09584c9c55e3513975a0f8f0524873370eb74904aa8f2b000'
DROP_ID_XOR=0xd4f63573
PREFIX_DROP_ID_XOR=0x0d8f6f4f
SCHEMA_SHA='4c34f65428983b06cf206534992623e6c427a2e8138c97e0ec2757bbdeb686ba'
# Native D9A110/D9A550 encode the template as the first big-endian i32.
# Private original-reader checks: analysis/ground-loot-20261015/native-items.json.
# Keep every remaining byte pinned; never trust client-provided quantity/options.
GROUND_FOOD=frozenset((70000,70010,70020,70030,70040,70050))
GROUND_ED=frozenset((127000,127010,127020))
GROUND_TEMPLATES=GROUND_FOOD|GROUND_ED|{77000}

@functools.lru_cache(maxsize=1)
def native_modes():
    path=PROJECT_ROOT/'analysis/client-6c6b5180/native-d0-modes.json';raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SCHEMA_SHA:raise ValueError('Native D0 schema changed')
    s=json.loads(raw)
    # The catalog retains its build-machine path as provenance. Runtime must
    # use the bundled witness on the deployment host, with the same pinned hash.
    native_image=PROJECT_ROOT/'analysis/client-6c6b5180/20261014-015631/native-d0-serializer.bin'
    if s['client_sha256']!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709' or s['stream_mode']!=0 or s['body_size']!=320 or s['body_sha256']!=BODY_SHA or hashlib.sha256(native_image.read_bytes()).hexdigest()!=s['native_image_sha256']:raise ValueError('Native D0 source mismatch')
    if [m['mode'] for m in s['modes']]!=list(range(20)):raise ValueError('Missing native D0 modes')
    return s['modes']

def decode_mode(payload,mode):
    cursor=0;v={}
    for spec in mode['fields']:
        field=spec['field'];mask=spec.get('xor',0)
        if field=='opaque':
            if cursor+4>len(payload):raise ValueError('Pickup nonce length truncated')
            n=struct.unpack_from('>I',payload,cursor)[0];cursor+=4
            if n>2048 or cursor+n>len(payload):raise ValueError('Pickup nonce bound')
            v[field]=payload[cursor:cursor+n];cursor+=n
        elif field=='item':
            body=payload[cursor:cursor+320]
            if len(body)!=320:raise ValueError('Truncated native pickup body')
            template=struct.unpack_from('>I',body)[0]
            from els_server.domain.dungeon_equipment_loot_rules import TEMPLATES as EQUIPMENT_LOOT_TEMPLATES
            from els_server.domain.dungeon_loot_catalog import TEMPLATES as NORMAL_LOOT_TEMPLATES,descriptor
            if template in NORMAL_LOOT_TEMPLATES:descriptor(template)
            from els_server.domain.dungeon_material_loot_catalog import TEMPLATES as MATERIAL_TEMPLATES,descriptor as material_descriptor
            if template in MATERIAL_TEMPLATES:material_descriptor(template)
            from els_server.domain.dungeon_source_loot import TEMPLATES as SOURCE_TEMPLATES,descriptor as source_descriptor
            if template in SOURCE_TEMPLATES:source_descriptor(template)
            if template not in GROUND_TEMPLATES|EQUIPMENT_LOOT_TEMPLATES|NORMAL_LOOT_TEMPLATES|SOURCE_TEMPLATES or hashlib.sha256(struct.pack('>I',77000)+body[4:]).hexdigest()!=BODY_SHA:
                raise ValueError('Unverified native pickup request body')
            v['template']=template
            cursor+=320
        elif field=='drop_id':
            if cursor+4>len(payload):raise ValueError('Pickup ID truncated')
            v[field]=struct.unpack_from('>I',payload,cursor)[0]^mask;cursor+=4
        elif field=='flag':
            if cursor>=len(payload):raise ValueError('Pickup flag truncated')
            v[field]=payload[cursor]^mask;cursor+=1
        else:
            if field not in ('player_xyz','drop_xyz') or cursor+12>len(payload):raise ValueError('Pickup XYZ truncated')
            v[field]=struct.unpack_from('>3f',payload,cursor);cursor+=12
    if cursor!=len(payload) or not 1<=v['drop_id']<2**31 or v['flag']!=0:raise ValueError('Pickup identity/flag/length mismatch')
    if any(not math.isfinite(x) or abs(x)>1_000_000 for field in ('player_xyz','drop_xyz') for x in v[field]):raise ValueError('Pickup coordinate bound')
    return {'drop_id':v['drop_id'],'template':v['template'],'quantity':1,'player_xyz':v['player_xyz'],'drop_xyz':v['drop_xyz'],'opaque_suffix':v['opaque'],'layout':{2:'nonce_first',4:'body_first'}.get(mode['mode'],'mode_'+str(mode['mode'])),'native_mode':mode['mode']}

def ground_pickup_request(payload):
    if not isinstance(payload,bytes) or not 353<=len(payload)<=2401:
        raise ValueError('Unverified pickup size')
    matches=[]
    for mode in native_modes():
        try:matches.append(decode_mode(payload,mode))
        except ValueError:pass
    if len(matches)!=1:raise ValueError('Unknown or ambiguous native pickup mode')
    return matches[0]

# Compatibility for older callers and recorded potion regressions.
potion_pickup_request=ground_pickup_request
