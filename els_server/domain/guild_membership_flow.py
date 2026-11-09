"""Finite native creation and explicit online master invitation/acceptance.

No guild economy, skill mutation, bank, territory or administrative joins.
All writes and every peer mailbox frame are prepared before SQLite commits.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
import time
from els_server.domain.guild_license_flow import (_facts as town_facts, reply_capture, guarded_reply,
    _app, _identity, _mailbox)
from els_server.domain.guild_initial_profile import profile
from els_server.domain.party_commands import _prepared_boxes
from els_server.protocol import guild_membership_messages as request
from els_server.protocol import guild_membership_profile as wire
from els_server.storage import guild_membership_state as state

WRITER_ENABLED = True


def _license_fallback(s, item_uid):
    """Anchor a stale instance number onto the one owned license.

    A rebuilt save renumbers inventory rows while the native client keeps the
    previous number, so the create request can name an instance this character
    never owned. Only a character holding exactly one unlocked singleton
    license is resolved that way; anything ambiguous keeps the strict path.
    """
    path=Path(s.account.store.path).resolve().as_uri()+'?mode=ro'
    with closing(sqlite3.connect(path,uri=True,timeout=10)) as db:
        if db.execute('SELECT 1 FROM inventory_items WHERE owner=? AND uid=?',
                      (s.account.uid,item_uid)).fetchone() is not None:
            return None
        rows=[row[0] for row in db.execute(
            'SELECT uid FROM inventory_items WHERE owner=? AND template=? AND metadata=0 '
            'AND bag_group=4 AND count=1 ORDER BY uid',(s.account.uid,state.LICENSE))]
    return rows[0] if len(rows)==1 else None


def facts(s):
    if getattr(s,'guild_agit',None)is not None:
        from els_server.domain.guild_agit_flow import bank_capture,identity
        from els_server.domain.housing_room_flow import world_state
        bank_capture(s);refs,values=identity(s);world,world_values=world_state(s)
        base=(tuple(map(id,refs)),values,tuple(map(id,world)),world_values,id(s.guild_agit),s.guild_agit['guild'],s.phase)
    else:base = town_facts(s)
    app=_app(s);identity=_identity(s);registry=getattr(app,'registry',None)
    box=_mailbox(s)
    if (identity['id'] != s.account.account_id
            or (registry is not None and not registry.enabled(s.account.account_id))
            or app.world.dungeons.room(s) is not None):
        raise ValueError('Guild current enabled account and town')
    return (base,id(s),id(getattr(s,'identity',None)),id(app.world),
            id(box),tuple(box.messages),tuple(box.moves.items()),box.bytes)


def _peer(s, *, uid=0, name=''):
    peers=[]
    for p in tuple(s.application.playing.values()):
        if uid and p.account.uid != uid:continue
        if name and p.account.character_identity()['name'] != name:continue
        facts(p)
        if Path(p.account.store.path).resolve()!=Path(s.account.store.path).resolve():
            raise ValueError('Guild peers use different character databases')
        peers.append(p)
    if len(peers)!=1:raise ValueError('Guild target must be the exact online character')
    return peers[0]


def cold(s):
    # Called after ordinary2A selection. Read-only; no optional-table creation.
    if s.client_build!='dx11_260923' or s.account.characters is None:return []
    with state.snapshot_connection(s.account.store.path)as db:
        db.execute('BEGIN')
        saved=state.snapshot(db,s.account.uid,s.account.account_id)
        return [] if saved is None else [wire.full_notification(profile(saved,db=db))]


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in (0x276,0x285,0x288,0x6c8):return None
    reply_guard=reply_capture(s)
    if reply_guard is None:return []
    try:
        if (not WRITER_ENABLED or not s.item_test or s.client_build!='dx11_260923'
                or type(sequence) is not int or not 1<=sequence<2**32
                or event.performers not in ((),(0,)) or event.payload_mode!=0
                or event.uid!=2**64-1 or event.target_uid!=2**64-1):
            raise ValueError('Guild native admission envelope')
        captured={s:facts(s)};boxes={}
        def guard():
            if any(facts(p)!=v for p,v in captured.items()):
                raise ValueError('Guild actor/source/mailbox changed during transaction')
            for p in captured:
                if getattr(p,'guild_agit',None)is not None:
                    from els_server.domain.guild_agit_flow import bank_capture
                    bank_capture(p)[1](db)
        operation=s.shop_session_id+':guild:'+str(s.account.uid)+':'+str(sequence)
        path=s.account.store.path
        with closing(sqlite3.connect(path,timeout=10)) as db:
            try:
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('BEGIN IMMEDIATE');guard();now=int(time.time())
                if event.kind==0x6c8:
                    answer=state.decline(db,s.account.uid,s.account.account_id,s.shop_session_id,event.payload,operation,now,guard)
                elif event.kind==0x276:
                    item_uid,name,message=request.create_request(event.payload)
                    import struct as _struct
                    resolved=_license_fallback(s,item_uid) or item_uid
                    payload=(event.payload if resolved==item_uid
                             else _struct.pack('>Q',resolved)+event.payload[8:])
                    def encode(saved,changes,repeat):
                        p=profile(saved,db=db)
                        return (wire.create_ack(p['basic'],changes),wire.full_notification(p))
                    answer=state.create(db,s.account.uid,s.account.account_id,resolved,name,message,
                        payload,operation,now,encode=encode,guard=guard)
                elif event.kind==0x285:
                    name,uid=request.invite_request(event.payload);peer=_peer(s,uid=uid,name=name)
                    captured[peer]=facts(peer)
                    def encode(saved,inviter,target):
                        nonlocal boxes
                        answer=(wire.invite_ack(peer.account.character_identity()['name']),)
                        deliveries=[(peer,[wire.invitation(profile(saved,db=db)['basic'],inviter,saved['system']['rules'])])]
                        boxes=_prepared_boxes(deliveries,answer)
                        return answer
                    answer=state.invite(db,s.account.uid,s.account.account_id,peer.account.uid,
                        peer.account.account_id,s.shop_session_id,peer.shop_session_id,event.payload,
                        operation,now,encode=encode,guard=guard)
                else:
                    guild_id,inviter,response=request.join_reply_request(event.payload)
                    if response!=0:raise ValueError('Only explicit native acceptance joins')
                    peer=_peer(s,name=inviter);captured[peer]=facts(peer)
                    def encode(saved,changes,repeat):
                        nonlocal boxes
                        p=profile(saved,db=db)
                        answer=(wire.accepted_ack(),wire.full_notification(p,joined=True))
                        boxes=_prepared_boxes([] if repeat else [(peer,[wire.full_notification(p)])],answer)
                        return answer
                    answer=state.accept(db,s.account.uid,s.account.account_id,guild_id,inviter,
                        s.shop_session_id,event.payload,operation,now,encode=encode,guard=guard,
                        inviter_account_id=peer.account.account_id,inviter_session=peer.shop_session_id)
                guard();db.commit()
            except BaseException:
                db.rollback();raise
        # No await/worker handoff between final fences, commit and assignment.
        for peer,box in boxes.items():peer.mailbox=box
        if event.kind in(0x276,0x288):
            for peer in captured:peer._guild_timing=None
        return list(answer)
    except (ValueError,UnicodeError,sqlite3.Error,OverflowError):
        if event.kind==0x6c8:return []
        return guarded_reply(reply_guard,lambda:[wire.failed(event.kind)])
