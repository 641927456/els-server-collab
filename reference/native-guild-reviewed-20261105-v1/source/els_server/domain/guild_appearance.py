"""Original501 worn-item/title projection for actual ready GuildAgit peers.

20F0710 reads UID, DD46E0 item records, title and an optional DB2880 map.
The optional map retains its original empty constructor value.
"""
from contextlib import closing
import sqlite3,struct
from els_server.protocol.protocol_codec import Event,encode_event


def projection(db,s,changes=()):
    from els_server.storage.inventory_state import load_items
    from els_server.storage.titles import equipped
    worn={i['slot']:i for i in load_items(db,s.account.uid) if i['group']==9}
    for (group,slot),item in changes:
        if group==9:
            if item is None:worn.pop(slot,None)
            else:worn[slot]=item
    return worn,equipped(db,s.account.uid)


def notification(uid,current,previous):
    from els_server.domain.fashion_state import record,empty_record
    worn,title=current;old=previous[0] if previous is not None else {}
    slots=sorted(set(worn)|set(old))
    return Event(0x201,kind=0x501,payload=struct.pack('>QI',uid,len(slots))+
        b''.join(record(worn[slot]) if slot in worn else empty_record(9,slot) for slot in slots)+
        struct.pack('>iI',title,0))


def prepare(db,s,*,changes=()):
    from els_server.domain.guild_agit_flow import bank_capture,_peers
    from els_server.domain.party_commands import _prepared_boxes
    _,guard=bank_capture(s);guard(db)
    context=s.guild_agit;current=projection(db,s,changes)
    notice=notification(s.account.uid,current,context.get('appearance'))
    encode_event(notice)
    peers=_peers(s,context['guild'])
    boxes=_prepared_boxes([(p,[notice]) for p,_,_ in peers],[])
    for _,_,pg in peers:pg(db)
    guard(db)
    return context,current,boxes


def deliver(s,publications):
    for context,current,boxes in publications:
        for peer,box in boxes.items():peer.mailbox=box
        context['appearance']=current
    return ()


def observe(s):
    if s.phase!='guild_agit_ready':return
    from els_server.domain.guild_agit_flow import bank_capture
    _,guard=bank_capture(s)
    with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
        db.execute('BEGIN');guard(db)
        current=projection(db,s)
        if current==s.guild_agit.get('appearance'):return
        publication=prepare(db,s)
    deliver(s,[publication])
