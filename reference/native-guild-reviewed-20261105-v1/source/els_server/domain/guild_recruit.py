"""Public advertisements and explicit applications, through saved membership."""
from contextlib import closing
from datetime import datetime,timezone,timedelta
from pathlib import Path
import json,sqlite3,struct,time
from els_server.protocol.social_messages import Reader
from els_server.protocol import guild_recruit_messages as wire
from els_server.protocol import guild_system_messages as notice
from els_server.protocol import guild_membership_profile as profile_wire
from els_server.protocol.protocol_codec import encode_event
from els_server.storage import guild_membership_state as members,guild_system_state as system
from els_server.domain import guild_rules as rules
from els_server.domain.guild_initial_profile import profile

KINDS=frozenset((0x2be,0x2c2,0x2c4,0x2c6,0x2c8,0x2ca,0x2cc,0x6ae))
READS=frozenset((0x2be,0x2c8,0x6ae))


def date(now):
    return datetime.fromtimestamp(now,timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')


def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS native_guild_applications_v2(
        owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL,
        guild_id INTEGER NOT NULL REFERENCES native_guilds(id),message TEXT NOT NULL,
        created_at INTEGER NOT NULL,expires_at INTEGER NOT NULL,source_operation TEXT NOT NULL UNIQUE)''')


def clear_application(db,owner):
    if system.exists(db,'native_guild_applications_v2'):
        db.execute('DELETE FROM native_guild_applications_v2 WHERE owner=?',(owner,))


def _ad(db,guild,now,*,expired=False):
    row=db.execute('SELECT g.name,g.master_uid,g.created_at,c.name FROM native_guilds g JOIN characters c ON c.uid=g.master_uid WHERE g.id=?',(guild,)).fetchone()
    if row is None:return None
    state=system.read(db,guild);ad=state['advertisement']
    if ad is None or not expired and ad['end']<=now:return None
    count=db.execute('SELECT COUNT(*) FROM native_guild_members WHERE guild_id=?',(guild,)).fetchone()[0]
    weekly=sum(d['weekly_honor']for d in state['member_details'].values()if d['honor_week']==rules.week(now))
    return dict(id=guild,name=row[0],master=row[3],founded=date(row[2]),created=row[2],
        level=rules.level(state['experience']),experience=state['experience'],members=count,capacity=state['capacity'],
        message=ad['message'],registered=date(ad['registered']),registration=ad['registered'],end=date(ad['end']),
        type=ad['type'],extra=0,weekly=weekly)


def _application(db,owner,now):
    if not system.exists(db,'native_guild_applications_v2'):return None
    row=db.execute('SELECT a.*,c.name,c.unit_class,c.level FROM native_guild_applications_v2 a JOIN characters c ON c.uid=a.owner WHERE a.owner=? AND a.expires_at>?',(owner,now)).fetchone()
    if row is None:return None
    return dict(zip(('owner','account','guild','message','created','expires','operation','name','class_id','level'),row),date=date(row[4]))


def _command(db,s,event,saved,operation,now):
    r=Reader(event.payload);kind=event.kind;owner=s.account.uid;notes=[];joined=None
    if kind==0x6ae:
        guild=r.scalar('i');r.end()
        row=db.execute('SELECT master_uid FROM native_guilds WHERE id=?',(guild,)).fetchone()if system.exists(db,'native_guilds')else None
        if row is None:raise ValueError('Guild preview source no longer exists')
        account=db.execute('SELECT account_id FROM character_owners WHERE uid=?',row).fetchone()[0]
        target=members.snapshot(db,row[0],account)
        from els_server.domain.guild_skills import page_profile
        from els_server.domain.guild_emblems import rows as emblem_rows
        from els_server.protocol.guild_membership_profile import pages_wire
        from els_server.protocol.guild_emblem_messages import collection
        state=target['system']
        body=(bytes(4)+wire.text(target['name'])+wire.text(target['master_name'])
            +struct.pack('>BHH',rules.level(state['experience']),len(target['members']),state['capacity'])
            +wire.text(target['message'])+struct.pack('>i',state['experience'])
            +pages_wire({int(k):page_profile(state,p,now)for k,p in state['pages'].items()})
            +wire.text(date(target['created_at']))+collection(emblem_rows(state,now,equipped_only=True))+wire.text(state['rules']))
        return [notice.reply(0x6af,body)],[],None,0,{}
    if kind==0x2be:
        sort=r.scalar('b');page=r.scalar('I');search=r.text(100);category=r.scalar('i');vacancy=r.scalar('B');low=r.scalar('B');high=r.scalar('B');r.end()
        if sort not in range(5)or page<1 or category not in range(4)or vacancy not in(0,1)or not 1<=low<=high<=99:raise ValueError('Guild advertisement filters')
        ads=[]
        if system.exists(db,'native_guilds'):
            for guild, in db.execute('SELECT id FROM native_guilds'):
                row=_ad(db,guild,now)
                if row and search.casefold()in row['name'].casefold()and category in(0,row['type'])and(not vacancy or row['members']<row['capacity'])and low<=row['level']<=high:ads.append(row)
        keys=('registration','created','weekly','members','level')
        ads.sort(key=lambda a:(a[keys[sort]],a['id']),reverse=True)
        pages=max(1,(len(ads)+14)//15);page=min(page,pages)
        return [wire.advertisements(sort,pages,page,ads[(page-1)*15:page*15],
            bool(saved and saved['grade']in(1,2)),bool(saved and _ad(db,saved['id'],now)))],[],None,0,{}
    if kind==0x2c8:
        page=r.scalar('I');r.end();rows=[];ads=[]
        if saved:
            if saved['grade']not in(1,2):raise ValueError('Guild application list authority')
            if system.exists(db,'native_guild_applications_v2'):
                rows=[_application(db,uid,now)for uid, in db.execute('SELECT owner FROM native_guild_applications_v2 WHERE guild_id=? AND expires_at>? ORDER BY created_at,owner',(saved['id'],now))]
        else:
            row=_application(db,owner,now)
            if row:
                ad=_ad(db,row['guild'],now,expired=True)
                if ad:rows=[row];ads=[ad]
        # Current UI sends 0 and consumes the complete vector itself.
        if page!=0:raise ValueError('Native guild application query page')
        return [wire.applications(saved['name']if saved else '',1,0,rows,ads)],[],None,0,{}
    if kind in(0x2c2,0x2c4):
        days=r.scalar('h');message=r.text(100);category=r.scalar('i');r.end()
        if saved is None or saved['grade']not in(1,2)or not rules.permission(saved,saved['system'],3):raise ValueError('Guild advertisement/funds authority')
        if days not in range(1,6)or not message.strip()or category not in range(1,4):raise ValueError('Guild advertisement fields')
        old=saved['system']['advertisement'];active=bool(old and old['end']>now)
        if active!=(kind==0x2c4):raise ValueError('Guild advertisement registration state')
        digest=system.receipt(db,owner,kind,event.payload,operation)[0]
        system.record(db,operation,digest,saved['id'],owner,kind,{},now)
        coins,_=system.change_currency(db,saved['id'],-days*2,0,operation,'guild-advertisement',now)
        saved['system']['advertisement']=dict(message=message,type=category,registered=now,end=now+days*86400)
        system.write(db,saved['id'],saved['system'])
        answer=[wire.registered(kind,days,message,coins)]
        notes=[notice.reply(0x7ec,struct.pack('>i',coins))]
        return answer,notes,None,saved['id'],{}
    if kind==0x2c6:
        guild=r.scalar('i');message=r.text(100);delete=r.scalar('B');r.end()
        ad=_ad(db,guild,now)if system.exists(db,'native_guilds')else None
        if saved is not None or ad is None or ad['members']>=ad['capacity']or not message.strip()or delete not in(0,1):raise ValueError('Guild application eligibility')
        previous=_application(db,owner,now)
        if previous and not delete:raise ValueError('Explicit replacement of old guild application required')
        schema(db);clear_application(db,owner)
        end=system.read(db,guild)['advertisement']['end']+7*86400
        db.execute('INSERT INTO native_guild_applications_v2 VALUES(?,?,?,?,?,?,?)',(owner,s.account.account_id,guild,message,now,end,operation))
        return [notice.result(0x2c7)],[],None,guild,dict(application_guild=guild)
    if kind==0x2ca:
        target=r.scalar('Q');r.end()
        if saved is None or saved['grade']not in(1,2):raise ValueError('Guild application acceptance authority')
        application=_application(db,target,now)
        if application is None or application['guild']!=saved['id']:raise ValueError('Current saved guild application required')
        account=application['account'];members._actor(db,target,account)
        if members.snapshot(db,target,account)is not None or len(saved['members'])>=saved['system']['capacity']:raise ValueError('Applicant already joined or guild filled')
        digest=system.receipt(db,owner,kind,event.payload,operation)[0]
        db.execute('INSERT INTO native_guild_actions VALUES(?,?,?,?,?,?)',(operation,digest,target,kind,saved['id'],now))
        db.execute('INSERT INTO native_guild_members VALUES(?,?,?,?,?,?)',(target,account,saved['id'],6,now,operation))
        db.execute('DELETE FROM native_guild_invitations WHERE target_uid=?',(target,));clear_application(db,target)
        db.execute('UPDATE native_guilds SET revision=revision+1 WHERE id=?',(saved['id'],))
        joined=(target,account)
        notes=[notice.notice(0,target,application['name'])]
        return [wire.accepted(application['name'])],notes,joined,saved['id'],dict(target=target,account=account,application=application['operation'])
    target=r.scalar('Q');guild=r.scalar('i');r.end()
    if saved is None:
        # The guildless board sends the applicant's own UID plus selected guild.
        if target!=owner:raise ValueError('Guild application cancellation owner')
        application=_application(db,owner,now)
        if application is None or application['guild']!=guild:raise ValueError('Guild application cancellation source')
    else:
        if saved['grade']not in(1,2):raise ValueError('Guild application rejection authority')
        application=_application(db,target,now)
        if application is None or application['guild']!=saved['id']:raise ValueError('Guild application rejection source')
    clear_application(db,target)
    return [notice.result(0x2cd)],[],None,application['guild'],{}


def failure(kind):
    if kind==0x6ae:return [notice.reply(0x6af,struct.pack('>iIIBHHIIIIII',1,0,0,0,0,0,0,0,0,0,0,0))]
    if kind==0x2be:return []  # Native ACK has no error word; never fabricate a successful empty query.
    if kind in(0x2c2,0x2c4):return [wire.registered(kind,0,'',0,1)]
    if kind==0x2c8:return [wire.applications('',0,0,(),(),1)]
    if kind==0x2ca:return [wire.accepted('',1)]
    return [notice.result(kind+1,1)]


def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind not in KINDS:return None
    from els_server.domain.guild_system_flow import capture,_envelope
    from els_server.domain.guild_license_flow import reply_capture
    from els_server.domain.party_commands import _prepared_boxes
    boxes={};fences={}
    try:
        same,guard=capture(s);_envelope(s,event,sequence)
        operation=s.shop_session_id+':guild-recruit:'+str(s.account.uid)+':'+str(sequence)
        with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
            try:
                db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN'if event.kind in READS else 'BEGIN IMMEDIATE')
                guard(db);members._actor(db,s.account.uid,s.account.account_id)
                saved=members.snapshot(db,s.account.uid,s.account.account_id);now=int(time.time())
                digest,old=system.receipt(db,s.account.uid,event.kind,event.payload,operation)
                joined=None;notes=[]
                if old:
                    result=old[1]
                    if result.get('target'):
                        target=members.snapshot(db,result['target'],result['account'])
                        if target is None or target['id']!=old[0]:raise ValueError('Applicant membership changed after original acceptance')
                    elif saved is not None and saved['id']!=old[0]:raise ValueError('Recruitment receipt belongs to another guild')
                    answer=[notice.reply(k,bytes.fromhex(payload))for k,payload in result['events']]
                    if event.kind in(0x2c2,0x2c4):
                        if saved is None:raise ValueError('Advertiser left original guild')
                        days,message=struct.unpack_from('>h',event.payload)[0],Reader(event.payload[2:]).text(100)
                        answer=[wire.registered(event.kind,days,message,system.currency(db,saved['id'])[0])]
                else:
                    if event.kind not in READS:members._schema(db)
                    # Advertisement debits require their operation before ledger entry.
                    answer,notes,joined,guild,result=_command(db,s,event,saved,operation,now)
                    if event.kind not in READS:
                        result['events']=[(e.kind,e.payload.hex())for e in answer]
                        if event.kind in(0x2c2,0x2c4):system.finish(db,operation,result)
                        else:system.record(db,operation,digest,guild,s.account.uid,event.kind,result,now)
                own=[];deliveries=[]
                for peer in tuple(s.application.playing.values()):
                    if Path(peer.account.store.path).resolve()!=Path(s.account.store.path).resolve():continue
                    selected=joined and peer.account.uid==joined[0]and peer.identity['id']==joined[1]
                    guild_peer=saved is not None and peer.account.uid in saved['members']
                    if not selected and not guild_peer:continue
                    events=list(notes)
                    if selected:
                        target=members.snapshot(db,*joined)
                        events=[profile_wire.full_notification(profile(target,db=db,now=now),joined=True)]
                    if not events:continue
                    if peer is s:own.extend(events);continue
                    lease=reply_capture(peer)
                    if lease is None:continue
                    fences[peer]=(lease,peer.mailbox,tuple(peer.mailbox.messages),tuple(peer.mailbox.moves.items()),peer.mailbox.bytes)
                    deliveries.append((peer,events))
                for e in answer+own:encode_event(e)
                boxes=_prepared_boxes(deliveries,answer+own)
                guard(db)
                for peer,(lease,box,msgs,moves,size)in fences.items():
                    lease()
                    if peer.mailbox is not box or (tuple(box.messages),tuple(box.moves.items()),box.bytes)!=(msgs,moves,size):raise ValueError('Guild recruitment peer mailbox changed')
                db.commit()
            except BaseException:db.rollback();raise
        for peer,box in boxes.items():peer.mailbox=box
        if joined:
            for peer in fences:
                if peer.account.uid==joined[0]:peer._guild_timing=None
        return answer+own
    except(ValueError,sqlite3.Error,UnicodeError,OverflowError):
        return failure(event.kind)if 'same'in locals()and same()else []
