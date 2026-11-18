"""Pinned correction of observed invalid ground-model references only."""
from pathlib import Path
import hashlib,json
EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'

def source(snapshot,executable_sha256):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:
        raise ValueError('Ground models native identity')
    aliases={'DropItemApple':'DroptItemApple','DropItemDrop_Weapon_Add':'DropItemDrop_Weapon_ADD',
        'DropItemDrop_Weapon_Rose':'DropItemDrop_Weapon_Common',
        'HQ_Shop_Item_160950.dds':'DropItemPouch',
        'HQ_Shop_INT_Event_AC_Upbody_100000151.dds':'DropItemPouch',
        'HQ_Shop_INT_Event_AC_Upbody_100000152.dds':'DropItemPouch'}
    for part in('Upbody','Lowbody','Hand','Foot'):
        for role in('ADD','Add','Ara','EL'):
            aliases[f'DropItemDrop_{part}_{role}']=f'DropItemDrop_{part}_Common'
    text=Path(__file__).with_suffix('.js').read_text('utf8')
    pins={0x97a980:snapshot[0x97a980:0x97a988].hex(),0x103237a:snapshot[0x103237a:0x1032390].hex()}
    for token,value in(('__GROUND_MODEL_ALIASES__',aliases),('__GROUND_MODEL_PINS__',pins)):
        if text.count(token)!=1:raise ValueError('Ground models composition anchor')
        text=text.replace(token,json.dumps(value))
    return text
