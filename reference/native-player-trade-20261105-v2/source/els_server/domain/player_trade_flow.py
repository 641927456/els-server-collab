"""Native two-party consent, editable offers and final atomic settlement.

World operations run under the existing world lock. The approved local rule
has no level or waiting-period admission restriction.
"""
from contextlib import closing,ExitStack
from pathlib import Path
import copy,sqlite3,time
from els_server.domain.friend_flow import selected
from els_server.domain.party_commands import _prepared_boxes
from els_server.domain.equipment_engrave_flow import current_lease
from els_server.protocol import player_trade_messages as wire
from els_server.storage import player_trade_state as storage


class Actor:
    def __init__(self,session,world):
        self.session=session;self.world=world
        self.refs,self.values=self.binding()
        self.owner,self.account,self.generation,self.scene=self.values
        self.path=Path(session.account.store.path).resolve()

    def binding(self):
        s=self.session
        refs,values=selected(s)
        if (s.phase!='town_ready' or s not in self.world.members
                or s.dungeon_return_pending or s.town_warp_transition is not None
                or self.world.dungeons.room(s)is not None):
            raise ValueError('Personal trade requires a current town character')
        # Mailboxes are intentionally excluded from the lifetime binding:
        # each successful peer publication replaces its cloned mailbox.
        return refs[:-1],(*values,self.world.members[s])

    def current(self):
        try:refs,values=self.binding()
        except ValueError:return False
        return values==self.values and all(a is b for a,b in zip(refs,self.refs))

    def check(self,db,now):
        if not self.current():
            raise ValueError('Personal trade character generation or scene changed')
        return storage.source(db,self.owner,self.account,now)


class PlayerTrades:
    def __init__(self,world):
        self.world=world;self.by_session={};self.next_id=900001

    def targets(self,session,function,args):
        room=self.by_session.get(session)
        if room is not None:return tuple(p.session for p in room['actors'])
        if getattr(function,'__name__',None)!='handle'or len(args)!=1:return ()
        event=args[0]
        if event.event_id!=0x202 or event.kind!=0x174:return ()
        try:target=wire.request(event.kind,event.payload)['target']
        except (ValueError,UnicodeError):return ()
        return tuple(p for p in self.world.members if p.account.uid==target)

    def people(self,room,db,now):
        people=room['actors']
        if (len({p.path for p in people})!=1 or len({p.scene for p in people})!=1
                or len({p.account for p in people})!=2
                or any(self.by_session.get(p.session)is not room for p in people)):
            raise ValueError('Personal trade room is no longer current')
        return {p.owner:p.check(db,now)for p in people}

    def read(self,actors):
        return closing(sqlite3.connect(actors[0].path.as_uri()+'?mode=ro',uri=True,timeout=10))

    def publish(self,deliveries,response,mutate):
        with ExitStack()as locks:
            for s in sorted({s for s,_ in deliveries},key=lambda s:s.identity['id']):
                locks.enter_context(s.mailbox.lock)
            boxes=_prepared_boxes(deliveries,response)
            mutate()
            for s,box in boxes.items():s.mailbox=box
        return response

    def forget(self,room):
        for actor in room['actors']:
            if self.by_session.get(actor.session)is room:self.by_session.pop(actor.session)

    def disconnect(self,session):
        room=self.by_session.get(session)
        if room is None:return
        # Remove the reservation even if a slow recipient cannot take a notice.
        self.forget(room)
        for actor in room['actors']:
            peer=actor.session
            if peer is not session and actor.current():
                self.world.send(peer,wire.cancelled(0x72))

    def synchronize(self,session):
        room=self.by_session.get(session)
        if room is None:return
        try:
            with self.read(room['actors'])as db:
                db.execute('BEGIN');self.people(room,db,int(time.time()))
        except (ValueError,sqlite3.Error):self.disconnect(session)

    def periodic(self,session):
        room=self.by_session.get(session)
        if room is None or room['phase']!='invited'or time.monotonic()<room['expires']:return
        self.forget(room)
        for actor,other in((room['actors'][0],room['actors'][1]),(room['actors'][1],room['actors'][0])):
            if actor.current():
                self.world.send(actor.session,wire.denied(other.owner,-1))

    def request(self,s,event,sequence):
        if event.event_id!=0x202 or event.kind not in wire.REQUESTS:return None
        kind=event.kind;account=s.account;uid=account.uid
        try:
            self.periodic(s)
            if (event.performers not in((),(0,))or event.uid!=event.target_uid
                    or event.uid!=2**64-1 or event.payload_mode!=0
                    or type(sequence)is not int or not 0<sequence<2**32):
                raise ValueError('Native personal trade envelope')
            parsed=wire.request(kind,event.payload)
            if kind==0x174:return self.invite(s,parsed['target'])
            room=self.by_session.get(s)
            if room is None:raise ValueError('No current personal trade')
            with self.read(room['actors'])as db:
                db.execute('BEGIN');now=int(time.time());saved=self.people(room,db,now)
                if kind==0x17a:
                    return self.publish([(p.session,[wire.cancelled(parsed['reason'])])for p in room['actors']],
                        [wire.acknowledgement(kind)],lambda:self.forget(room))
                if kind==0x177:return self.answer(s,room,parsed,saved)
                if room['phase']!='open':raise ValueError('Trade invitation has not been accepted')
                if kind in(0x17f,0x182):return self.update(s,room,kind,parsed,db,now,saved)
                self.verify(room,db,now,saved)
                if kind==0x185:
                    if uid in room['registered']:return[wire.acknowledgement(kind)]
                    return self.publish([(p.session,[wire.registered(uid)])for p in room['actors']],
                        [wire.acknowledgement(kind)],lambda:room['registered'].add(uid))
                if room['registered']!={p.owner for p in room['actors']}:
                    raise ValueError('Both trade offers must be registered')
                if uid in room['approved']:return[wire.acknowledgement(kind)]
                if not room['approved']:
                    return self.publish([(p.session,[wire.approved(uid)])for p in room['actors']],
                        [wire.acknowledgement(kind)],lambda:room['approved'].add(uid))
            return self.complete(s,room)
        except (ValueError,sqlite3.Error,UnicodeError,OverflowError):
            if kind==0x188:self.disconnect(s)
            if s.account is not account or s.account.uid!=uid or not current_lease(s):return[]
            if kind==0x177:return[wire.denied(parsed.get('target',0)if 'parsed'in locals()else 0,-1)]
            return[wire.acknowledgement(kind,result=-1)]

    def invite(self,s,target):
        if not 1001<=target<2**63 or s in self.by_session:raise ValueError('Trade requester is busy or target invalid')
        other=next((p for p in self.world.members if p.account.uid==target),None)
        if other is not None:self.periodic(other)
        if other is None or other is s or other in self.by_session:raise ValueError('Trade target is absent or busy')
        actors=[Actor(s,self.world),Actor(other,self.world)]
        if len({p.account for p in actors})!=2 or len({p.path for p in actors})!=1 or len({p.scene for p in actors})!=1:
            raise ValueError('Trade requires two accounts in the same town')
        with self.read(actors)as db:
            db.execute('BEGIN');now=int(time.time())
            for p in actors:p.check(db,now)
            names=[db.execute('SELECT name FROM characters WHERE uid=?',(p.owner,)).fetchone()[0]for p in actors]
        # Current176 passes the float10.0 at43714DC to2FF0A90; its30 field
        # is the displayed invitation countdown. Match that bounded lifetime.
        room=dict(id=self.next_id,actors=actors,phase='invited',expires=time.monotonic()+10,
            offers={p.owner:dict(ed=0,items={})for p in actors},registered=set(),approved=set())
        def change():
            for p in actors:self.by_session[p.session]=room
            self.next_id+=1
        return self.publish([(other,[wire.invitation(actors[0].owner,names[0])])],
            [wire.acknowledgement(0x174,target=target,name=names[1])],change)

    def answer(self,s,room,parsed,saved):
        first,second=room['actors']
        if room['phase']!='invited'or s is not second.session or parsed['target']!=first.owner:
            raise ValueError('Only the invited current recipient can answer')
        if not parsed['accept']:
            return self.publish([(first.session,[wire.denied(second.owner,-1)])],[],lambda:self.forget(room))
        rows=[dict(uid=p.owner,account_id=p.account,name=p.session.account.character()['name'],ed=saved[p.owner]['money']['ed'])for p in room['actors']]
        return self.publish([(first.session,[wire.created(room['id']),wire.joined(rows[1])])],
            [wire.created(room['id']),wire.members(rows)],lambda:room.update(phase='open'))

    def update(self,s,room,kind,parsed,db,now,saved):
        uid=s.account.uid
        if uid in room['registered']or room['approved']:raise ValueError('Registered offer is immutable')
        offers=copy.deepcopy(room['offers']);offer=offers[uid]
        if kind==0x17f:
            source=parsed['uid']
            if parsed['delete']:
                if source not in offer['items']:raise ValueError('Removing an unoffered instance')
                item=offer['items'].pop(source)['item']
            else:
                if source in offer['items']:raise ValueError('Instance already offered; remove it before changing quantity')
                # Current UI2FF8310/2FF9159 admits a new entry only below10.
                if len(offer['items'])>=10:raise ValueError('Personal trade ten item slots are full')
                item=storage.offered(db,saved[uid],source,parsed['count'],now)
                offer['items'][source]=dict(item=item,quantity=parsed['count'])
            shown=dict(item,count=parsed['count']if not parsed['delete']else item['count'])
            notice=wire.item_changed(uid,shown,parsed['delete'],{p.owner:False for p in room['actors']})
        else:
            if not 0<=parsed['ed']<=min(saved[uid]['money']['ed'],saved[uid]['trade_limit']):
                raise ValueError('Personal trade owned ED bound')
            offer['ed']=parsed['ed'];notice=wire.ed_changed(uid,offer['ed'],{p.owner:False for p in room['actors']})
        def change():room['offers']=offers;room['registered'].clear();room['approved'].clear()
        return self.publish([(p.session,[notice])for p in room['actors']],[wire.acknowledgement(kind)],change)

    def verify(self,room,db,now,saved):
        for actor in room['actors']:
            uid=actor.owner;offer=room['offers'][uid];current=saved[uid]
            if not 0<=offer['ed']<=min(current['trade_limit'],current['money']['ed']):raise ValueError('Offered ED no longer owned')
            for row in offer['items'].values():
                if storage.offered(db,current,row['item']['uid'],row['quantity'],now)!=row['item']:
                    raise ValueError('Registered item changed')

    def complete(self,s,room):
        def current():
            return dict(id=room['id'],participants=[dict(owner=p.owner,account=p.account,generation=p.generation,
                ed=room['offers'][p.owner]['ed'],items=list(room['offers'][p.owner]['items'].values()))for p in room['actors']])
        agreement=copy.deepcopy(current());approved=set(room['approved'])
        operation=room['actors'][0].generation+':trade:'+str(room['id'])
        boxes={}
        with ExitStack()as locks:
            def guard(db,now):
                self.people(room,db,now)
                if (room['phase']!='open'or room['registered']!={p.owner for p in room['actors']}
                        or room['approved']!=approved or len(approved)!=1 or s.account.uid in approved
                        or current()!=agreement):
                    raise ValueError('Trade confirmations changed')
            def encode(db,results,repeated):
                nonlocal boxes
                events={p.session:[wire.completed(results[p.owner]['ed'],results[p.owner]['changes'])]for p in room['actors']}
                response=[wire.acknowledgement(0x188),wire.approved(s.account.uid),*events[s]]
                deliveries=[]
                for p in sorted(room['actors'],key=lambda p:p.session.identity['id']):
                    locks.enter_context(p.session.mailbox.lock)
                    if p.session is not s:deliveries.append((p.session,[wire.approved(s.account.uid),*events[p.session]]))
                boxes=_prepared_boxes(deliveries,response)
                return response
            response=storage.perform(room['actors'][0].path,agreement,operation,guard,encode)
            self.forget(room)
            for peer,box in boxes.items():peer.mailbox=box
        return response
