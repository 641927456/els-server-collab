"""Map30000 resource spawns encoded for pinned 2F7BF50 stream mode3.

Order and XOR keys: native branch 2F7CB84..2F7CF7B, terminal 2F80EC3.
Resource-to-DTO copies: F9F670. Other vectors/maps are empty.
"""
from els_server.paths import PROJECT_ROOT
import json,struct
from pathlib import Path
FIELDS=[
 (0x19,4,0,'empty'),(0,4,0xe5688f23,'scalar'),(9,12,0,'scalar'),
 (0x61,1,0,'scalar'),(0x15,4,0x8a0c839c,'scalar'),(8,1,0x1e,'scalar'),
 (0x64,1,0,'scalar'),(4,4,0xa2aaf136,'scalar'),(0x66,1,0,'scalar'),
 (0x4e,1,0,'scalar'),(0x4f,4,0x7765c04b,'scalar'),(0x53,1,0,'scalar'),
 (0x77,2,0,'scalar'),(0x79,1,0,'scalar'),(0x7a,1,0,'scalar'),
 (0x7c,4,0,'scalar'),(0x80,1,0,'scalar'),(0x81,4,0xbfeb4567,'scalar'),
 (0x85,4,0x78c6a83c,'scalar'),(0x89,4,0xe738fe1d,'scalar'),(0x8d,4,0x0df03661,'scalar'),
 (0x91,1,0,'scalar'),(0x92,1,0,'scalar'),(0x93,1,0,'scalar'),
 (0x94,4,0,'empty'),(0x31,4,0,'empty'),(0x55,12,0,'scalar'),
 (0x49,4,0xf0f3b8ae,'scalar'),(0x6c,1,0x27,'scalar'),(0x67,4,0,'scalar'),
 (0x54,1,0,'scalar'),(0x65,1,0,'scalar'),(0x63,1,0,'scalar'),
 (None,4,0,'empty'),(0x6b,1,0xdb,'scalar'),(0x7b,1,0x5f,'scalar'),
 (0x6d,8,0x0afe164622482246,'scalar'),(0x76,1,0x86,'scalar'),
 (0x62,1,0,'scalar'),(0x75,1,0x53,'scalar'),(0x4d,1,0,'scalar')]
MODE0_FIELDS=[
 (0x66,1,0,'scalar'),(0x65,1,0,'scalar'),(0x67,4,0,'scalar'),
 (0x6b,1,0xa8,'scalar'),(0x64,1,0,'scalar'),(0x63,1,0,'scalar'),
 (None,4,0,'empty'),(0x7b,1,0x17,'scalar'),(0x75,1,0xae,'scalar'),
 (0x76,1,0x17,'scalar'),(0x6d,8,0x39cb1d467db8934e,'scalar'),
 (0x62,1,0,'scalar'),(0x6c,1,0x83,'scalar'),(0x15,4,0x1f5b3263,'scalar'),
 (9,12,0,'scalar'),(0,4,0x8d0dbb13,'scalar'),(0x19,4,0,'empty'),
 (4,4,0xaa1cb53c,'scalar'),(8,1,0x45,'scalar'),(0x61,1,0,'scalar'),
 (0x55,12,0,'scalar'),(0x4f,4,0xf0debbe2,'scalar'),(0x53,1,0,'scalar'),
 (0x77,2,0,'scalar'),(0x79,1,0,'scalar'),(0x7a,1,0,'scalar'),
 (0x7c,4,0,'scalar'),(0x80,1,0,'scalar'),(0x81,4,0x1a6f3e4d,'scalar'),
 (0x85,4,0xac398527,'scalar'),(0x89,4,0xbd41af6e,'scalar'),
 (0x8d,4,0x29296f82,'scalar'),(0x91,1,0,'scalar'),(0x92,1,0,'scalar'),
 (0x93,1,0,'scalar'),(0x94,4,0,'empty'),(0x4e,1,0,'scalar'),
 (0x54,1,0,'scalar'),(0x31,4,0,'empty'),(0x4d,1,0,'scalar'),
 (0x49,4,0x8fd00a74,'scalar')]
COPIES=[(0,0,4),(4,4,4),(8,0x4f,4),(0xc,0x53,1),(0x28,0x15,4),
 (0x2c,0x4e,1),(0x2d,0x54,1),(0x30,0x55,12),(0x3c,8,1),
 (0x44,0x61,1),(0x45,0x62,1),(0x46,0x63,1),(0x47,0x64,1),
 (0x48,0x65,1),(0x50,0x66,1),(0x54,0x67,4),(0x58,0x77,2),
 (0x5a,0x79,1),(0x5c,0x7c,4),(0x60,0x80,1),(0x64,0x75,1),
 (0x88,0x85,4),(0x8c,0x89,4),(0x4c,0x76,1),(0x90,0x93,1)]

def resource_dto(raw):
    if len(raw)!=0x98:raise ValueError('NPC resource size')
    dto=bytearray(0xa4)
    dto[0x6b]=2;dto[0x6d:0x75]=bytes([255])*8
    for src,dst,n in COPIES:dto[dst:dst+n]=raw[src:src+n]
    return bytes(dto)

def encode_npc(dto,mode=3):
    if len(dto)!=0xa4:raise ValueError('NPC DTO size')
    if mode not in (0,3):raise ValueError('Unaudited NPC wire mode')
    wire=[]
    for off,n,key,kind in (MODE0_FIELDS if mode==0 else FIELDS):
        if kind=='empty':wire.append(bytes(n))
        elif n==12:
            wire.append(b''.join(dto[off+i:off+i+4][::-1] for i in (0,4,8)))
        else:wire.append((int.from_bytes(dto[off:off+n],'little')^key).to_bytes(n,'big'))
    return b''.join(wire)

def spawn_parts():
    data=json.loads((PROJECT_ROOT/'analysis/dungeon-npc-fixture.json').read_text(encoding='utf8'))
    if data['map']!=30000 or data['substage']!=0:raise ValueError('Unsupported NPC fixture')
    return data['parts']

def spawn_map():
    parts=spawn_parts();wire=struct.pack('>I',len(parts))
    for part in parts:
        npcs=part['npcs'];wire+=struct.pack('>iI',part['index'],len(npcs))
        wire+=b''.join(encode_npc(resource_dto(bytes.fromhex(n['bytes']))) for n in npcs)
    return wire

def updated_spawn_map(npc_key=None):
    """One local training NPC. This is not the retail population table."""
    data=json.loads((PROJECT_ROOT/'analysis/client-6c6b5180/npc-wire-candidate.json').read_text(encoding='utf8'))
    if (data['client_sha256']!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
        or (data['map'],data['substage'],data['part'],data['template'],data['key'])!=(30000,0,0,88,100001)):
        raise ValueError('Unsupported updated NPC fixture')
    dto=bytearray.fromhex(data['dto_hex'])
    wire=encode_npc(dto,mode=0)
    if wire.hex()!=data['wire_hex']:raise ValueError('NPC fixture differs from native-decoded wire')
    if npc_key is not None:
        if type(npc_key) is not int or not 0<=npc_key<80:raise ValueError('NPC slot test key')
        dto[:4]=struct.pack('<i',npc_key);wire=encode_npc(dto,mode=0)
    return struct.pack('>IiII',1,0,0,1)+wire

def updated_npc_init_map(npc_key=None):
    data=json.loads((PROJECT_ROOT/'analysis/client-6c6b5180/npc-init-candidate.json').read_text(encoding='utf8'))
    if data['client_sha256']!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709' or data['key']!=100001:
        raise ValueError('Unsupported NPC initialization fixture')
    wire=bytes.fromhex(data['wire_hex'])
    if len(wire)!=172 or data.get('template')!=88:raise ValueError('NPC initialization wire size/template')
    if npc_key is not None and (type(npc_key) is not int or not 0<=npc_key<80):raise ValueError('NPC slot test key')
    return struct.pack('>Ii',1,data['key'] if npc_key is None else npc_key)+wire

def gate_test_maps():
    """Isolated candidate; keys1/2 represent actual gate resource templates."""
    data=json.loads((PROJECT_ROOT/'analysis/client-6c6b5180/gate-test-fixture.json').read_text(encoding='utf8'))
    npcs=data['npcs']
    if (data['client_sha256']!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
            or (data['map'],data['substage'],data['part'])!=(30000,0,0)
            or [(n['key'],n['template']) for n in npcs]!=[(0,88),(1,625),(2,626)]):
        raise ValueError('Unsupported gate fixture')
    wires=[];initialization=[]
    for n in npcs:
        raw=bytes.fromhex(n['resource_hex'])
        if struct.unpack_from('<ii',raw)!=(n['key'],n['template']):raise ValueError('Gate resource identity')
        wire=encode_npc(resource_dto(raw),0)
        if wire.hex()!=n['wire_hex']:raise ValueError('Gate spawn fixture mismatch')
        init=bytes.fromhex(n['init_hex'])
        if struct.unpack_from('>i',init)[0]!=n['template']:raise ValueError('Gate initialization identity')
        wires.append(wire);initialization.append(struct.pack('>i',n['key'])+init)
    return (struct.pack('>IiII',1,0,0,len(npcs))+b''.join(wires),
            struct.pack('>I',len(npcs))+b''.join(initialization))
