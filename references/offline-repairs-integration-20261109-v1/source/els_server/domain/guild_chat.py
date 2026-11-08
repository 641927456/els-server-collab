"""Original85/86/87 guild chat and GuildAgit scene chat."""
from contextlib import closing
from pathlib import Path
import sqlite3
from els_server.protocol import social_messages as wire
from els_server.storage.guild_membership_state import snapshot

def deliver(world,session,text,now,channel=3):
    try:
        app=session.application;account=session.identity['id'];path=session.account.store.path
        from els_server.domain.guild_license_flow import reply_capture
        own_guard=reply_capture(session)
        if own_guard is None or channel not in(0,3):raise ValueError('Guild chat current lease/channel')
        scene_guard=None
        if channel==0:
            from els_server.domain.guild_agit_flow import bank_capture
            _,scene_guard=bank_capture(session)
        recipients=[];guards=[]
        with closing(sqlite3.connect(path))as db:
            db.execute('BEGIN')
            saved=snapshot(db,session.account.uid,account)
            if saved is None:raise ValueError('Guild chat membership required')
            member_accounts=dict(db.execute('SELECT owner,account_id FROM native_guild_members WHERE guild_id=?',(saved['id'],)))
            if scene_guard:scene_guard(db)
            for peer in tuple(app.playing.values()):
                if(peer.role!='game'or peer.phase not in('town_ready','guild_agit_ready','dungeon_active','photo_zone_admitted','wedding_hall')
                    or Path(peer.account.store.path).resolve()!=Path(path).resolve()):continue
                if member_accounts.get(peer.account.uid)!=peer.identity['id']:continue
                context=getattr(peer,'guild_agit',None)
                if channel==0 and(peer.phase!='guild_agit_ready'or context is None or context['guild']!=saved['id']or context.get('revoked')):continue
                guard=reply_capture(peer)
                if guard is not None:recipients.append(peer);guards.append(guard)
            notice=wire.chat_notice(session.account.character(),account,text,channel)
            from els_server.domain.party_commands import _prepared_boxes
            boxes=_prepared_boxes([(p,[notice])for p in recipients],[wire.chat_ack()])
            own_guard()
            if scene_guard:scene_guard(db)
            for guard in guards:guard()
        for peer,box in boxes.items():peer.mailbox=box
        session.chat_times.append(now)
        return [wire.chat_ack()]
    except(ValueError,sqlite3.Error,UnicodeError):return [wire.chat_ack(1)]
