"""Finite native creation and explicit online master invitation/acceptance.

No guild economy, skill mutation, bank, territory or administrative joins.
All writes and every peer mailbox frame are prepared before SQLite commits.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
import time
from els_server.domain.guild_license_flow import _facts as town_facts, reply_capture, guarded_reply
from els_server.domain.guild_initial_profile import profile
from els_server.domain.party_commands import _prepared_boxes
from els_server.protocol import guild_membership_messages as request
from els_server.protocol import guild_membership_profile as wire
from els_server.storage import guild_membership_state as state

WRITER_ENABLED = True


def facts(s):
    base = town_facts(s)
    if (s.identity['id'] != s.account.account_id
            or not s.application.registry.enabled(s.account.account_id)
            or s.application.world.dungeons.room(s) is not None):
        raise ValueError('Guild current enabled account and town')
    return (base,id(s),id(s.identity),id(s.application.world),
            id(s.mailbox),tuple(s.mailbox.messages),tuple(s.mailbox.moves.items()),s.mailbox.bytes)


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
    saved=state.cold(s.account.store.path,s.account.uid,s.account.account_id)
    return [] if saved is None else [wire.full_notification(profile(saved))]


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in (0x276,0x285,0x288):return None
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
        operation=s.shop_session_id+':guild:'+str(s.account.uid)+':'+str(sequence)
        path=s.account.store.path
        with closing(sqlite3.connect(path,timeout=10)) as db:
            try:
                db.execute('PRAGMA foreign_keys=ON')
                db.execute('BEGIN IMMEDIATE');guard();now=int(time.time())
                if event.kind==0x276:
                    item_uid,name,message=request.create_request(event.payload)
                    def encode(saved,changes,repeat):
                        p=profile(saved)
                        return (wire.create_ack(p['basic'],changes),wire.full_notification(p))
                    answer=state.create(db,s.account.uid,s.account.account_id,item_uid,name,message,
                        event.payload,operation,now,encode=encode,guard=guard)
                elif event.kind==0x285:
                    name,uid=request.invite_request(event.payload);peer=_peer(s,uid=uid,name=name)
                    captured[peer]=facts(peer)
                    def encode(saved,inviter,target):
                        nonlocal boxes
                        answer=(wire.invite_ack(peer.account.character_identity()['name']),)
                        deliveries=[(peer,[wire.invitation(profile(saved)['basic'],inviter,'')])]
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
                        p=profile(saved)
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
        return list(answer)
    except (ValueError,UnicodeError,sqlite3.Error,OverflowError):
        return guarded_reply(reply_guard,lambda:[wire.failed(event.kind)])
