"""Finite current-CN item records and explicitly approved local Ariel rewards."""
import functools,hashlib,struct
from els_server.game_data import client_data

NEW_RECORDS={
710079:'b90d7c72a4c8f279115b95de0a5a36d34db51f654ec19ca88c58e714fc62f42d',
715753:'81cfec045f12ae8c5c5649095db5d57e57dc5b86c1e8a418236b159f4c7eb699',
720016:'eca89f1195c9112470cd5764ae168203b71722da2b8a7e6578038e334393330f',
721051:'e07bd5c61a02956f5a791d2d2625c4a0faab4e88d0d6438b0287e9ff75339b0c',
721053:'d4d5a5f161706c957870213915b563e0683ed0a9e4fee611929652aa1a6163f8',
721054:'8664ef12c0ccc0e66c574fcb58980affcc4ec4d8a7e93b7b7b6727008dde72f5',
721055:'b037080c797c04ecc5f6be15a9a29858e4b39a469872196d956df4b1f3a76321',
721056:'f9b29d2bd13e095fce61a946872b62fe0d5005c09c0f3189c6403fc1b7644153'}
REWARDS=((721053,200),(721055,1),(715753,1),(710084,30),(721054,1),
         (721056,1),(721053,200),(118189,2),(715753,1),(720016,5),
         (721055,1),(710193,30),(721053,200),(721056,1),(710079,30))

@functools.lru_cache(maxsize=1)
def definitions():
    rows={}
    for template,pin in NEW_RECORDS.items():
        item=client_data().item(template);raw=item['record']
        if len(raw)!=232 or hashlib.sha256(raw).hexdigest()!=pin:raise ValueError('Ariel current item record changed')
        flags4,flags8=struct.unpack_from('<II',raw,4);kind=(flags8>>3)&31
        # Pinned original19803A0 jump-table cases5/7, not an item-name guess.
        if flags4&33 or kind not in(5,7):raise ValueError('Ariel native inventory classification')
        group={5:6,7:4}[kind];metadata=raw[7]&15;native_stack=struct.unpack_from('<I',raw,16)[0]
        if metadata==0:
            if not flags4&(1<<22)or native_stack!=0:raise ValueError('Ariel native singleton record')
            maximum=1
        else:
            if metadata!=2 or not 1<=native_stack<=1000:raise ValueError('Ariel native stack record')
            maximum=native_stack
        rows[template]=dict(template=template,metadata=metadata,group=group,max_stack=maximum)
    return rows

@functools.lru_cache(maxsize=1)
def rewards():
    from els_server.domain.ariel_attendance_preview import rows
    expected={7737+i:((t,q,0),)for i,(t,q)in enumerate(REWARDS)}
    if rows()!=expected:raise ValueError('Approved Ariel15-slot reward authority changed')
    return tuple(dict(index=i,template=t,quantity=q)for i,(t,q)in enumerate(REWARDS))

def grant_plan(template,quantity,moment):
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    if template not in({t for t,q in REWARDS}|{721051})or type(quantity)is not int or not 1<=quantity<=999:
        raise ValueError('Ariel finite grant source')
    rewards();definitions()
    plan=dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=quantity)
    if template in(721055,721056):plan['expires_at']=moment+90*86400
    elif template==721051:plan['expires_at']=moment+30*86400
    return plan
