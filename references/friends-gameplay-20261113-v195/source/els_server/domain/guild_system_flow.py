"""Native guild window and shared membership commands, on the real session."""
from contextlib import closing
from datetime import datetime,timezone,timedelta
from pathlib import Path
import sqlite3,struct,time
from els_server.protocol.social_messages import Reader
from els_server.protocol.protocol_codec import encode_event
from els_server.protocol import guild_system_messages as wire
from els_server.protocol import guild_membership_profile as profile_wire
from els_server.storage import guild_membership_state as members,guild_system_state as system
from els_server.storage.guild_coin_state import contributions
from els_server.domain import guild_rules as rules
from els_server.domain.guild_initial_profile import profile
from els_server.domain import guild_farm,guild_shop,guild_skills,guild_consumables,guild_fountain,guild_emblems,guild_skins,guild_rename,guild_expedition

KINDS=frozenset((0x279,0x27b,0x27d,0x27f,0x28c,0x28e,0x290,0x292,0x294,0x648,0x6a9,0x6ab,0x84f,0x853,0xac9,0xacd))|guild_farm.KINDS|guild_shop.KINDS|guild_skills.KINDS|guild_consumables.KINDS|guild_fountain.KINDS|guild_emblems.KINDS|guild_skins.KINDS|guild_rename.KINDS|guild_expedition.KINDS
READS=frozenset((0x279,0x27b,0x27f,0x84f,0xacd))|guild_farm.READS|guild_emblems.READS|guild_skills.READS|guild_skins.READS

def capture(s):
    if getattr(s,'guild_agit',None)is not None:
        from els_server.domain.guild_agit_flow import bank_capture
        return bank_capture(s)
    from els_server.domain.housing_access_flow import capture as town
    return town(s)

def _envelope(s,event,sequence):
    if (not s.item_test or s.client_build!='dx11_260923' or event.performers not in((),(0,))
        or event.payload_mode!=0 or event.uid!=2**64-1 or event.target_uid!=2**64-1
        or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Guild native envelope')

def _posted(state,owner,now):
    return sum(p['owner']==owner and p['day']==rules.day(now)for p in state['posts'])

def _roster(db,s,saved,page,view,now):
    if view not in range(4) or view!=3 and page<1:raise ValueError('Guild roster page/type')
    live={p.account.uid:p for p in tuple(s.application.playing.values())if Path(p.account.store.path).resolve()==Path(s.account.store.path).resolve()}
    coins=contributions(db,saved['id'])
    rows=[]
    for uid,account,name,class_id,level,grade,joined in db.execute('''SELECT m.owner,m.account_id,c.name,c.unit_class,c.level,m.grade,m.joined_at
        FROM native_guild_members m JOIN characters c ON c.uid=m.owner WHERE m.guild_id=? ORDER BY m.grade,m.owner''',(saved['id'],)):
        detail=system.member(saved['system'],uid);peer=live.get(uid)
        online=peer is not None and peer.identity['id']==account and s.application.registry.enabled(account)
        rows.append(dict(uid=uid,account=account,name=name,class_id=class_id,level=level,grade=grade,channel=1 if online else 0,
            map=peer.active_map if online else 0,position=0 if online else -1,login=joined if online else 0,
            logout=detail['last_login'],greeting=detail['message'],honor=detail['honor'],
            weekly_honor=detail['weekly_honor']if detail['honor_week']==rules.week(now)else 0,
            combat=0,coins=coins.get((uid,account),0)))
    if view==0:rows.sort(key=lambda r:(r['position']==-1,r['grade'],r['uid']))
    pages=max(1,(len(rows)+12)//13)
    online=sum(r['position']!=-1 for r in rows)
    # 3247AB0 supplies no page for view 3. 2407CB0 paginates the returned list.
    if view==3:return wire.roster(1,pages,view,online,rows)
    if page>pages:raise ValueError('Guild roster outside actual pages')
    return wire.roster(page,pages,view,online,rows[(page-1)*13:page*13])

def _command(db,s,event,saved,operation,now,notices):
    if event.kind in guild_expedition.KINDS:return guild_expedition.command(db,s,event,saved,operation,now,notices=notices)
    if event.kind in guild_rename.KINDS:return guild_rename.command(db,s,event,saved,operation,now)
    if event.kind in guild_skins.KINDS:return guild_skins.command(db,s,event,saved,operation,now)
    if event.kind in guild_emblems.KINDS:return guild_emblems.command(db,s,event,saved,operation,now)
    if event.kind in guild_fountain.KINDS:return guild_fountain.command(db,s,event,saved,operation,now)
    if event.kind in guild_skills.KINDS:return guild_skills.command(db,s,event,saved,operation,now)
    if event.kind in guild_shop.KINDS:return guild_shop.command(db,s,event,saved,operation,now)
    if event.kind in guild_farm.KINDS:return guild_farm.command(db,s,event,saved,operation,now)
    if event.kind in guild_consumables.KINDS:
        answer,notes,template=guild_consumables.command(db,s,event,saved,operation,now)
        return answer,notes
    state=saved['system'];owner=s.account.uid;r=Reader(event.payload);kind=event.kind;notifications=[]
    if kind==0x279:
        page=r.scalar('I');view=r.scalar('b');r.end()
        return [_roster(db,s,saved,page,view,now)],notifications
    if kind==0x27b:
        r.end();return [wire.menu(10-_posted(state,owner,now))],notifications
    if kind==0x84f:
        r.end();return [wire.join_rules(state['rules'])],notifications
    if kind==0xacd:
        r.end();return [guild_expedition.summary(saved,now)],notifications
    if kind==0x27f:
        page=r.scalar('I');category=r.scalar('B');search=r.scalar('i');r.end()
        if page<1 or category>2 or search not in range(5):raise ValueError('Guild board selection')
        posts=[p for p in reversed(state['posts'])if not p.get('deleted') and category in(0,1) and (category==0 or search==0 or p['category']==search)]
        pages=max(1,(len(posts)+12)//13)
        if page>pages:raise ValueError('Guild board outside actual pages')
        return [wire.posts(page,pages,category,posts[(page-1)*13:page*13])],notifications
    if kind==0x27d:
        category=r.scalar('B');message=r.text(100);r.end()
        if not message.strip()or category not in range(1,5) or _posted(state,owner,now)>=10:raise ValueError('Guild board daily limit/category')
        identity=db.execute('SELECT name,level FROM characters WHERE uid=?',(owner,)).fetchone()
        identity_number=state.get('next_post',1);state['next_post']=identity_number+1
        state['posts'].append(dict(id=identity_number,owner=owner,category=category,grade=saved['grade'],level=identity[1],name=identity[0],
            date=datetime.fromtimestamp(now,timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S'),text=message,day=rules.day(now)))
        answer=[wire.reply(0x27e,struct.pack('>iB',0,10-_posted(state,owner,now)))]
    elif kind==0x6a9:
        identity=r.scalar('Q');r.end()
        post=next((p for p in state['posts']if p['id']==identity and not p.get('deleted')),None)
        if post is None or post['owner']!=owner and saved['grade']not in(1,2):raise ValueError('Guild post deletion authority')
        post['deleted']=True;answer=[wire.result(0x6aa)]
    elif kind==0x28c:
        target=r.scalar('Q');grade=r.scalar('B');r.end()
        row=db.execute('SELECT name FROM characters WHERE uid=?',(target,)).fetchone()
        if row is None:raise ValueError('Guild grade target')
        system.grade(db,saved,target,grade)
        answer=[wire.grade_ack(row[0],grade)]
        notifications.append(wire.notice(1,target,row[0],value=grade))
        if grade==1:notifications.append(wire.notice(1,owner,saved['master_name'],value=2))
    elif kind==0x28e:
        message=r.text(100);r.end()
        if not rules.permission(saved,state,1):raise ValueError('Guild announcement authority')
        db.execute('UPDATE native_guilds SET message=?,revision=revision+1 WHERE id=?',(message,saved['id']))
        answer=[wire.result(0x28f)];notifications.append(wire.notice(8,owner,message=message))
    elif kind==0x290:
        target=r.scalar('Q');kicked=r.scalar('B');r.end()
        if kicked not in(0,1)or bool(kicked)!=(target!=owner):raise ValueError('Guild leave selector')
        if not kicked and getattr(s,'guild_agit',None)is not None:raise ValueError('Return from GuildAgit before leaving membership')
        row=db.execute('SELECT name FROM characters WHERE uid=?',(target,)).fetchone()
        if row is None:raise ValueError('Guild leave target')
        state=system.leave(db,saved,target,operation,now)
        answer=[wire.leave_ack(target,bool(kicked))]
        notifications.append(wire.notice(2,target,row[0]))
        if kicked:notifications.append(wire.notice(7,target,row[0]))
    elif kind==0x292:
        target=r.scalar('Q');message=r.text(100);r.end()
        if target!=owner:raise ValueError('Guild greeting owner')
        system.member(state,owner)['message']=message
        answer=[wire.greeting_ack(not message)];notifications.append(wire.notice(5,owner,message=message))
    elif kind==0x648:
        # 3129660 sends the member's start-in-agit preference on leaving play.
        enabled=r.scalar('B');r.end()
        if enabled not in (0,1):raise ValueError('GuildAgit start preference')
        system.member(state,owner)['start_in_agit']=bool(enabled)
        answer=[]
    elif kind==0xac9:
        message=r.text(100);r.end()
        if not rules.permission(saved,state,1):raise ValueError('Guild notice authority')
        state['announcement']=message;state['announcement_author']=owner
        answer=[wire.reply(0xaca,bytes(4)+wire.text(message)+struct.pack('>Q',owner))]
        notifications=[wire.reply(0xacb,wire.text(message)+struct.pack('>Q',owner))]
    elif kind==0x853:
        message=r.text(100);r.end()
        if saved['grade']not in(1,2):raise ValueError('Guild application rules authority')
        state['rules']=message;answer=[wire.reply(0x854,bytes(4)+wire.text(message))]
    elif kind==0x6ab:
        if saved['grade']!=1:raise ValueError('Only actual master configures guild authorities')
        if r.scalar('I')!=6:raise ValueError('Complete six-rank authority map required')
        authorities={};names={}
        for _ in range(6):
            grade=r.scalar('B');flags=[r.scalar('B')for _ in range(4)];count=r.scalar('B');name=r.text()
            honor=r.scalar('i');maximum=r.scalar('i')
            if(grade not in range(1,7)or str(grade)in authorities or any(f not in(0,1)for f in flags)
                or not 0<=count<=rules.calls('SetGuildBankWithdrawalCountLimit')[0][0]
                or not 0<=honor<=rules.calls('SetGuildBankWithdrawalReqHonorPointLimit')[0][0]
                or not 0<=maximum<=20000 or grade==1 and flags!=[1,1,1,1]):raise ValueError('Guild authority fields')
            authorities[str(grade)]=[*map(bool,flags),count,honor,maximum];names[str(grade)]=name
        r.end();state['authorities']=authorities;state['grade_names']=names
        from els_server.domain.guild_bank_rules import permissions_wire,permission_rows
        answer=[wire.reply(0x6ac,bytes(4)+permissions_wire(permission_rows(state)))]
        notifications=[profile_wire.full_notification(profile(saved,db=db,now=now))]
    elif kind==0x294:
        r.end()
        if saved['grade']!=1 or saved['members']!=(owner,)or s.phase!='town_ready':raise ValueError('Guild disband requires sole master in normal town')
        guild_expedition.depart(db,saved,owner,now)
        from els_server.storage.guild_quests import depart as abandon_tasks
        abandon_tasks(db,owner)
        # Native disband confirmation permanently deletes the guild. Personal
        # inventory, awarded mail and immutable inventory receipts stay owned.
        for table in('native_guild_bank_items_v1','native_guild_bank_transfers_v1','native_guild_bank_history_v1',
            'native_guild_bank_expansions_v1','native_guild_coin_donations_v1','native_guild_coin_v1',
            'native_guild_name_requests_v2','native_guild_currency_entries_v2','native_guild_system_v2','native_guild_invitations','native_guild_applications_v2','native_guild_members'):
            if system.exists(db,table):db.execute('DELETE FROM '+table+' WHERE guild_id=?',(saved['id'],))
        db.execute('DELETE FROM native_guilds WHERE id=?',(saved['id'],))
        return [wire.result(0x295),_quest_reset(db,owner,now)],[]
    else:raise ValueError('Guild command is not registered')
    system.write(db,saved['id'],state)
    return answer,notifications

def _failure(kind):
    if kind in guild_expedition.KINDS:return guild_expedition.failure(kind)
    if kind in guild_rename.KINDS:return guild_rename.failure(kind)
    if kind in guild_skins.KINDS:return guild_skins.failure(kind)
    if kind in guild_emblems.KINDS:return guild_emblems.failure(kind)
    if kind in guild_consumables.KINDS:
        from els_server.protocol.career_messages import use_ack
        return use_ack(result=1)
    if kind in guild_fountain.KINDS:return guild_fountain.failure(kind)
    if kind in guild_skills.KINDS:return guild_skills.failure(kind)
    if kind in guild_shop.KINDS:return guild_shop.failure(kind)
    if kind in guild_farm.KINDS:return guild_farm.failure(kind)
    if kind==0x279:return wire.roster(1,1,0,0,(),1)
    if kind==0x27b:return wire.menu(0,1)
    if kind==0x27d:return wire.reply(0x27e,struct.pack('>iB',1,0))
    if kind==0x27f:return wire.posts(1,1,0,(),1)
    if kind==0x28c:return wire.grade_ack('',0,1)
    if kind==0x290:return wire.leave_ack(0,False,1)
    if kind==0x292:return wire.greeting_ack(False,1)
    if kind==0x84f:return wire.join_rules('',1)
    if kind==0xac9:return wire.reply(0xaca,struct.pack('>iIQ',1,0,0))
    if kind==0x853:return wire.reply(0x854,struct.pack('>iI',1,0))
    if kind==0xacd:return wire.expedition_summary(0,False,False,False,1)
    if kind==0x6ab:return wire.reply(0x6ac,struct.pack('>iI',1,0))
    return wire.result(kind+1,1)

def _quest_reset(db,owner,now):
    from els_server.storage.seal_quests import _state,ensure
    from els_server.storage.inventory_state import load_items
    from els_server.protocol.quest_messages import initialization
    ensure(db)
    return initialization(_state(db,owner,load_items(db,owner),now=now))


def _notifications(db,peer,saved,notes,now):
    result=[]
    kicked={struct.unpack_from('>Q',n.payload,1)[0]for n in notes if n.kind==0x284 and n.payload[0]==7}
    for note in notes:
        if note.kind==0x278:
            own=members.snapshot(db,peer.account.uid,peer.identity['id'])
            if own is None:raise ValueError('Guild profile recipient membership changed')
            result.append(profile_wire.full_notification(profile(own,db=db,now=now)))
        elif note.kind==0x284 and note.payload[0]in(2,7):
            target=struct.unpack_from('>Q',note.payload,1)[0]
            if note.payload[0]==7:
                if target==peer.account.uid:result.append(note)
            elif target!=peer.account.uid or target not in kicked:result.append(note)
            if note.payload[0]==2 and target!=peer.account.uid and peer.phase=='guild_agit_ready':
                departed=next((p for p in peer.application.playing.values()if p.account.uid==target),None)
                context=None if departed is None else getattr(departed,'guild_agit',None)
                if context is not None and context['guild']==saved['id'] and departed.phase=='guild_agit_ready':
                    from els_server.protocol.guild_agit_messages import removed
                    result.append(removed(target))
        else:result.append(note)
    if any(n.kind==0x284 and n.payload[0]in(2,7) and struct.unpack_from('>Q',n.payload,1)[0]==peer.account.uid for n in notes):
        result.append(_quest_reset(db,peer.account.uid,now))
    return result


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in KINDS:return None
    if event.kind==0xe44 and event.payload[-4:]!=struct.pack('>i',25):return None
    if event.kind in guild_consumables.KINDS and not guild_consumables.handles(s,event,sequence):return None
    boxes={};notices=[]
    try:
        same,guard=capture(s);_envelope(s,event,sequence)
        path=s.account.store.path;owner=s.account.uid;kind=event.kind
        operation=s.shop_session_id+':guild-system:'+str(owner)+':'+str(sequence)
        peer_fences={}
        def fence_peers():
            for peer,expected in peer_fences.items():
                current=(peer.account,peer.identity,peer.mailbox,peer.account.uid,peer.identity['id'],peer.shop_session_id,
                    peer.phase,tuple(peer.mailbox.messages),tuple(peer.mailbox.moves.items()),peer.mailbox.bytes)
                if(any(current[i]is not expected[i]for i in range(3))or current[3:]!=expected[3:]
                    or s.application.playing.get(peer.identity['id'])is not peer):raise ValueError('Guild peer lease or mailbox changed')
        with closing(sqlite3.connect(path,timeout=10))as db:
            try:
                db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN'if kind in READS else 'BEGIN IMMEDIATE')
                guard(db);members._actor(db,owner,s.account.account_id)
                saved=members.snapshot(db,owner,s.account.account_id)
                if saved is None:raise ValueError('Guild membership required')
                now=int(time.time())
                digest,old=system.receipt(db,owner,kind,event.payload,operation)
                if old is not None:
                    if old[0]!=saved['id']:raise ValueError('Guild receipt belongs to another membership')
                    answer=guild_shop.replay(db,saved,kind,event.payload,operation,digest,now)if kind in guild_shop.KINDS else guild_farm.replay(db,saved,kind,event.payload,operation,digest,now)if kind in guild_farm.KINDS else [wire.reply(k,bytes.fromhex(payload))for k,payload in old[1]['events']]
                    if kind in guild_skills.KINDS:
                        current=guild_skills.replay(db,saved,kind,event.payload,operation,digest,now)
                        if current is not None:answer=current
                    if kind in guild_consumables.KINDS:answer=guild_consumables.replay(db,saved,kind,event.payload,operation,digest,now,old[1]['template'])
                    if kind==0x7dd:answer=[wire.reply(0x7de,struct.pack('>ii',0,system.currency(db,saved['id'])[0]))]
                    if kind in guild_expedition.KINDS:answer=guild_expedition.replay(db,saved,kind,operation,digest,now,old[1],stage_number=event.payload[0],notices=notices)
                    if kind in guild_rename.KINDS:answer=guild_rename.replay(db,s,saved,kind,operation,digest,now,old[1])
                    if kind==0x84c:answer=[wire.reply(0x84d,struct.pack('>ii',0,saved['system']['skin']or 623))]
                    if kind in(0x7e3,0x7e5):answer=guild_emblems.replay(db,saved,kind,event.payload,now,old[1])
                    notifications=[]
                else:
                    if kind not in READS:members._schema(db)
                    if kind not in READS:system.record(db,operation,digest,saved['id'],owner,kind,{},now)
                    before_experience=saved['system']['experience']
                    answer,notifications=_command(db,s,event,saved,operation,now,notices)
                    from els_server.domain.gameplay_announcements import guild_level
                    notices.extend(guild_level(saved,before_experience))
                    if kind==0x298 and notifications:
                        from els_server.protocol.native_notice_messages import achievement
                        name=db.execute('SELECT name FROM native_guilds WHERE id=?',(saved['id'],)).fetchone()[0]
                        notices.append(achievement(11,saved['name'],name))
                    if kind not in READS:
                        result=dict(events=[(e.kind,e.payload.hex())for e in answer])
                        if kind in guild_consumables.KINDS:result['template']=struct.unpack_from('>i',answer[0].payload,len(answer[0].payload)-28)[0]
                        if result.get('template')in guild_consumables.guild_services.CONTRACTS:
                            buff=guild_consumables.guild_services.CONTRACTS[result['template']][0]
                            result['service']=dict(saved['system']['services'][str(buff)])
                        system.finish(db,operation,result)
                        if result.get('template')in guild_consumables.guild_services.CONTRACTS:
                            notifications.append(guild_consumables.guild_services.ui_notification(db,saved,now))
                own_notifications=_notifications(db,s,saved,notifications,now)
                for e in answer+own_notifications:encode_event(e)
                if notifications:
                    from els_server.domain.party_commands import _prepared_boxes
                    deliveries=[]
                    for peer in tuple(s.application.playing.values()):
                        if peer is s or Path(peer.account.store.path).resolve()!=Path(path).resolve():continue
                        # Include removed actors so the native consumer clears their old guild.
                        if peer.account.uid in saved['members']:
                            peer_fences[peer]=(peer.account,peer.identity,peer.mailbox,peer.account.uid,peer.identity['id'],peer.shop_session_id,
                                peer.phase,tuple(peer.mailbox.messages),tuple(peer.mailbox.moves.items()),peer.mailbox.bytes)
                            peer_events=_notifications(db,peer,saved,notifications,now)
                            deliveries.append((peer,peer_events))
                    boxes=_prepared_boxes(deliveries,answer+own_notifications)
                guard(db);fence_peers();db.commit()
            except BaseException:db.rollback();raise
        for peer,box in boxes.items():peer.mailbox=box
        from els_server.domain.gameplay_announcements import publish
        publish(s,notices)
        if kind in(0x219,0x28c,0x290,0x294):
            s._guild_timing=None
            for peer in peer_fences:peer._guild_timing=None
        if kind==0x290 and old is None:
            target=struct.unpack_from('>Q',event.payload)[0]
            for peer in peer_fences:
                context=getattr(peer,'guild_agit',None)
                if peer.account.uid==target and context is not None and context['guild']==saved['id']:context['revoked']=operation
        return answer+own_notifications
    except(ValueError,sqlite3.Error,UnicodeError,OverflowError):
        return [_failure(event.kind)]if event.kind!=0x648 and 'same'in locals()and same()else []
