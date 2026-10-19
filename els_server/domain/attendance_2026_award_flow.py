"""Opt-in selected518 quest claim, account-mail and original state projection.

BA8 explicitly uses the user-authorized LOCAL earliest-past-missed policy. The
catalog is the user's approved local definition, explicitly merged with the
other server reward rows. Existing default sessions never instantiate this.
"""
from contextlib import closing
from dataclasses import replace
import sqlite3,struct,uuid
from els_server.domain.attendance_2026_quests import AttendanceQuestBinding
from els_server.storage.attendance_2026_awards import AttendanceAwards
from els_server.storage.attendance_2026_progress import AttendanceProgress
from els_server.storage.inventory_state import load_items
from els_server.storage.seal_quests import load_character,current_slots
from els_server.protocol import attendance_2026_quest as quest_wire,attendance_2026_messages as wire,quest_messages as ordinary
from els_server.protocol.boosting_2026_restore import split
from els_server.protocol.protocol_codec import Event


class AttendanceAwardFlow(AttendanceQuestBinding):
    def __init__(self,definition,*,campaign,definition_sha256,schedule,clock,catalog,
                 deadline,sender,title,body,anchor_value,other_reward_rows,purchase_policy=None,task_policy=None):
        super().__init__(definition,campaign=campaign,definition_sha256=definition_sha256,schedule=schedule,clock=clock)
        if type(anchor_value) is not int or not 0 <= anchor_value <= schedule.available_from:
            raise ValueError('Explicit original BA5 anchor required')
        self.task_policy=task_policy
        self.purchase_policy=purchase_policy
        self.purchase_available=lambda s,t:self.schedule.period_at(t) is not None
        self.catalog=catalog;self.text=dict(deadline=deadline,sender=sender,title=title,body=body)
        self.anchor=anchor_value;self.reward_notice=catalog.notice(existing=other_reward_rows)
        self.token=uuid.uuid4().hex;self.last_state=None

    def _store(self,db):
        progress=AttendanceProgress(db,self.definition,campaign_id=self.campaign,definition_sha256=self.digest)
        return AttendanceAwards(progress,self.schedule,self.catalog,purchase_policy=self.purchase_policy,task_policy=self.task_policy,**self.text)

    def _state(self,s,operation):
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
            return getattr(self._store(db),operation)(account=s.account.account_id,character=s.account.uid,now=self.clock())

    def handle(self,s,event,sequence):
        if not self.enabled(s):return None
        if event.event_id==0x202 and event.kind==0xba8:
            def failure():
                with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
                    t=self._store(db)
                    try:
                        t._owner(s.account.account_id,s.account.uid)
                        state=t._attendance(s.account.account_id)
                    except ValueError:state=wire.AttendanceState(0,0,0)
                    ed=t._balances(s.account.uid)['ed']
                return [wire.purchase_reply(2005,ed,state)]
            if (s.phase not in ('town_ready','dungeon_active') or type(sequence) is not int or not 1<=sequence<2**32
                or event.performers!=(0,) or event.uid!=0xffffffffffffffff
                or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):return failure()
            try:
                wire.purchase_request(event.payload)
                now=self.clock()
                if not self.purchase_available(s,now):raise ValueError('Campaign is unavailable')
                with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
                    t=self._store(db)
                    out=t.purchase_next(account=s.account.account_id,character=s.account.uid,now=now,
                        operation=f'purchase:{self.token}:{sequence}',
                        encode=lambda result:wire.purchase_reply(0,result['balances']['ed'],result['attendance']).payload)
                return [Event(0x201,kind=0xba9,payload=out['response'])]
            except ValueError:return failure()
        if (event.event_id!=0x202 or event.kind!=0xf4 or len(event.payload)<4
                or struct.unpack_from('>i',event.payload)[0]!=166210):
            return super().handle(s,event,sequence)
        def failure(result=2005):
            inv=s.account.get_inventory_snapshot()
            return [ordinary.reward_ack(166210,s.account.character(),s.account.get_location(),s.account.get_skills(),inv['balances'],inv['items'],result=result)]
        if (s.phase not in ('town_ready','dungeon_active') or type(sequence) is not int or not 1<=sequence<2**32
                or event.performers!=(0,) or event.uid!=0xffffffffffffffff
                or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):return failure()
        try:
            request=ordinary.request(event.kind,event.payload)
            if request['npc']!=0:raise ValueError('Selected daily task has no NPC')
            with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
                t=self._store(db);location=s.account.get_location()
                def encode(out):
                    character=load_character(db,s.account.uid,s.account.account_id)
                    return ordinary.reward_ack(166210,character,location,current_slots(db,character),out['balances'],load_items(db,s.account.uid),
                        completed_at=out['completed_at'],replayed=out['replayed']).payload
                out=t.claim(account=s.account.account_id,character=s.account.uid,now=self.clock(),operation=f'claim:{self.token}:{sequence}',encode=encode)
            from els_server.domain.quest_flow import initialization
            return [Event(0x201,kind=0xf5,payload=out['response']),initialization(s)]
        except ValueError as error:
            return failure(187 if str(error) in ('Daily task requirements not met','Claim day already occupied','Campaign is unavailable') else 2005)

    def _projection(self,s):
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
            t=self._store(db);now=self.clock()
            with t._transaction():
                t._owner(s.account.account_id,s.account.uid)
                task=t._refresh(s.account.account_id,now);state=t._attendance(s.account.account_id)
                period=self.schedule.period_at(now)
                day=next((p.index for p in self.schedule.periods if p.key==period),None)
                done=db.execute('SELECT claimed_at FROM activity518_stamps WHERE campaign=? AND account=? AND day_index=? AND kind=?',
                    (self.campaign,s.account.account_id,day,'normal')).fetchone() if day is not None else None
            return task,state,None if done is None or task is not None else done[0]

    @staticmethod
    def _merge(event,view,completed_at):
        if event.event_id!=0x201 or event.kind!=0x2b:return event
        active,done,tail=split(event.payload)
        active=[raw for qid,raw in active if qid!=166210];done=[raw for qid,raw in done if qid!=166210]
        if view is not None:active.append(quest_wire.active_record(**view))
        elif completed_at is not None:done.append(ordinary.completed_record(dict(id=166210,completed_at=completed_at)))
        raw=bytes(4)+struct.pack('>I',len(active))+b''.join(active)+struct.pack('>I',len(done))+b''.join(done)+tail
        if len(raw)>65536:raise ValueError('Combined attendance quest map bound')
        return replace(event,payload=raw)

    def finalize(self,s,replies):
        if not self.enabled(s):return replies
        restoring=any(e.event_id==0x201 and e.kind in (0x2a,0x2b) for e in replies)
        if s.phase not in ('town_ready','dungeon_active') and not restoring:return replies
        character=s.account.character()
        if character is None or character['level']<10:return replies
        task,state,completed_at=self._projection(s)
        view=None if task is None else self.view(task,owner_uid=s.account.uid)
        out=[self._merge(e,view,completed_at) for e in replies]
        # An explicit full4B6 table precedes initial character state. Reject
        # another table rather than silently replacing another feature's rows.
        if any(e.event_id==0x201 and e.kind==0x2a for e in replies):
            if any(e.event_id==0x201 and e.kind==0x4b6 for e in replies):raise ValueError('Merge all reward rows before projection')
            out.insert(0,self.reward_notice)
        signature=(s.account.uid,None if task is None else task['accepted_at'],None if view is None else tuple(view.items()))
        if view is not None and signature!=self.last and not any(e.event_id==0x201 and e.kind in (0x2b,0xf0) for e in replies):
            out.append(quest_wire.progress(**view))
        self.last=signature
        signature=(s.account.uid,state.wire())
        if restoring or signature!=self.last_state:out.append(wire.state_notice(self.anchor,state))
        self.last_state=signature
        return out
