"""Native580 provider composed with the existing attendance/growth provider."""
import sqlite3,struct,time
from contextlib import closing
from dataclasses import replace
from els_server.domain import abyss_weapon_2026 as rules
from els_server.protocol import abyss_weapon_2026 as wire,quest_messages as quest_wire
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol.activity_2026_entries import CodeEntry,notice,read
from els_server.protocol.boosting_2026_restore import split
from els_server.storage.abyss_weapon_2026 import Campaign,exists,period,week
from els_server.storage.inventory_state import InventoryFull,load_items

def install(app):
    if app.config.mode!='friends'or app.config.profile!='integrated_dx11':return
    rules.register()
    with closing(sqlite3.connect(app.config.state_file,timeout=10))as db,db:
        db.execute('BEGIN IMMEDIATE');Campaign(db).initialize()
    previous=app.activity2026_awards_factory
    def factory(account):
        inner=previous(account)if previous is not None else None
        flow=Flow(inner)
        manager=getattr(app,'activity2026_manager',None)
        if manager is not None and inner in manager.flows:
            manager.flows.discard(inner);manager.flows.add(flow)
        return flow
    app.activity2026_awards_factory=factory

class Flow:
    def __init__(self,previous,*,clock=time.time):
        self.previous=previous;self.clock=clock;self.last=None;self.observed=None;self.codes={};self.active_keys=set()
        self.online=previous.online if previous is not None else None
    def __getattr__(self,name):
        if self.previous is not None:return getattr(self.previous,name)
        raise AttributeError(name)
    @staticmethod
    def enabled(s):return s.role=='game'and s.client_build=='dx11_260923'and s.item_test and s.account.store is not None and s.account.characters is not None and not getattr(s,'released',False)
    @staticmethod
    def guard(s,db):
        from els_server.domain.equipment_chip_flow import current_lease
        from els_server.storage.item_actor import require_active_character
        if not Flow.enabled(s)or s.account.store.uid!=s.account.uid or not current_lease(s):raise ValueError('Current selected campaign actor required')
        require_active_character(db,s.account.uid)
    def capture(self,s):
        if self.previous is not None:self.previous.capture(s)
        if not self.enabled(s)or not s.reward_test or s.phase!='dungeon_loading'or s.clear_notified or not s.reward_run_id:return
        with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
            t=Campaign(db);row=t.snapshot(s.account.account_id,s.account.uid)
            if row is None:return
            from els_server.domain.seal_quests import appropriate_level_range
            from els_server.game_data import client_data
            dungeon=s.dungeon_run.identity if s.dungeon_run is not None else s.dungeon_id
            definition=client_data().dungeon(dungeon)
            low,high=appropriate_level_range(definition)
            with db:
                db.execute('BEGIN IMMEDIATE');self.guard(s,db)
                t.admit(s.account.account_id,s.account.uid,s.reward_run_id,dungeon,low<=s.account.character_identity()['level']<=high,int(self.clock()))
    def prepare_clear(self,s):return self.previous.prepare_clear(s)if self.previous is not None else None
    def after_reply(self,s,replies):return self.previous.after_reply(s,replies)if self.previous is not None else replies
    def _task_records(self,t,s,now):
        active=[];done=[]
        for row in t.tasks(s.account.account_id,s.account.uid,now):
            if row['count']is None:continue
            count,claimed=row['count'];q=row['id']
            if claimed is None:active.append((q,wire.active(q,rules.quests()[q]['objective']['m_iID'],s.account.uid,count,rules.limit(q))))
            else:done.append((q,struct.pack('>iiQQ',q,1,claimed,0)))
        return active,done
    def _response(self,s,kind,result=2005):
        if kind==0xc5f:return [wire.converted(result)]
        return [wire.ack(0xc5c if kind==0xc5b else 0xc5e,result)]
    def handle(self,s,event,sequence):
        selected_point=False
        if self.enabled(s)and event.event_id==0x202 and event.kind==0x219 and len(event.payload)>=8:
            uid=struct.unpack_from('>Q',event.payload)[0]
            with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
                selected_point=db.execute('SELECT template FROM inventory_items WHERE uid=?AND owner=?',(uid,s.account.uid)).fetchone()==(rules.POINT_ITEM,)
                if not selected_point and type(sequence)is int and exists(db,'inventory_action_receipts'):
                    selected_point=bool(db.execute('SELECT 1 FROM inventory_action_receipts WHERE operation_id=?AND owner=?AND kind=0x219',(s.shop_session_id+':abyss-point:'+str(sequence),s.account.uid)).fetchone())
        qid=struct.unpack_from('>i',event.payload)[0]if len(event.payload)>=4 else None
        selected_task=event.kind in(0xee,0xf4,0xfa)and qid in rules.quests()
        selected=event.event_id==0x202 and(event.kind in(0xc5b,0xc5d,0xc5f)or selected_task or selected_point)
        if not selected:return self.previous.handle(s,event,sequence)if self.previous is not None else None
        if not self.enabled(s):return self._response(s,event.kind)
        def failure(code=2005):
            if selected_point:
                from els_server.protocol.career_messages import use_ack
                return [use_ack(template=rules.POINT_ITEM,ed=s.account.get_reward_balances()['ed'],result=code)]
            if event.kind==0xee:return [quest_wire.accept_ack(code)]
            if event.kind==0xfa:
                from els_server.domain.quest_flow import initialization
                return [initialization(s)]
            if selected_task:
                inv=s.account.get_inventory_snapshot()
                return [quest_wire.reward_ack(qid,s.account.character(),s.account.get_location(),s.account.get_skills(),inv['balances'],inv['items'],result=code)]
            return self._response(s,event.kind,code)
        if s.phase!='town_ready'or type(sequence)is not int or not 1<=sequence<2**32 or event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0:return failure()
        now=int(self.clock());out=[]
        try:
            if selected_point:
                from els_server.protocol.career_messages import use_request
                point_uid=use_request(event.payload)
            elif selected_task:
                request=quest_wire.request(event.kind,event.payload)
                if event.kind==0xfa:return failure()
                if request['npc']not in(0,10018,10025)or request.get('choices')or request.get('flags',(0,0,0,0,0))[1]:raise ValueError('Abyss task claim context')
            elif event.kind==0xc5d:
                if len(event.payload)!=1:raise ValueError('Original Abyss reward request is one byte')
                index=event.payload[0]
            elif event.payload:raise ValueError('Original Abyss join/convert body is empty')
            with closing(sqlite3.connect(s.account.store.path,timeout=10))as db,db:
                db.execute('BEGIN IMMEDIATE');self.guard(s,db);now=int(self.clock());t=Campaign(db)
                if selected_point:
                    from els_server.storage.abyss_weapon_points import use
                    out.append(use(db,s.account.account_id,s.account.uid,point_uid,event.payload,s.shop_session_id+':abyss-point:'+str(sequence)))
                elif event.kind==0xc5b:
                    updates=t.join(s.account.account_id,s.account.uid,now)
                    from els_server.domain.dungeon_drops import pickup_inventory_notice
                    if updates:out.append(pickup_inventory_notice(updates))
                    out.append(wire.ack(0xc5c,0))
                elif event.kind==0xc5d:
                    updates=t.claim_reward(s.account.account_id,s.account.uid,index)
                    from els_server.domain.dungeon_drops import pickup_inventory_notice
                    if updates:out.append(pickup_inventory_notice(updates))
                    out.append(wire.ack(0xc5e,0))
                elif event.kind==0xc5f:out.append(wire.converted(items=[t.convert(s.account.account_id,s.account.uid,now)]))
                else:
                    t.participant(s.account.account_id,s.account.uid);t.recover(s.account.account_id,s.account.uid,now)
                    if event.kind==0xee:out.append(quest_wire.accept_ack())
                    else:
                        at=t.claim_task(s.account.account_id,s.account.uid,qid,now)
                        from els_server.storage.seal_quests import load_character,current_slots
                        from els_server.storage.npc_trade import balances
                        character=load_character(db,s.account.uid,s.account.account_id)
                        out.append(quest_wire.reward_ack(qid,character,s.account.get_location(),current_slots(db,character),balances(db,s.account.uid),load_items(db,s.account.uid),completed_at=at))
                state=wire.state(t.snapshot(s.account.account_id,s.account.uid))
                # Native C5C immediately opens the window using its C5A state.
                if event.kind in(0xc5b,0xc5d):out.insert(len(out)-1,state)
                else:out.append(state)
                for message in out:encode_event(message)
                self.guard(s,db)
            self.last=None
            return out
        except InventoryFull:return failure(165)
        except ValueError:return failure()
    def _current_view(self,s,db,now,account,character,replies,*,recover):
        t=Campaign(db);row=t.snapshot(account,character)
        participant=row is not None
        refreshed=(character,week(now))!=self.observed or any(e.event_id==0x201 and e.kind in(0xf5,0xc23,0x113,0xd2d)for e in replies)
        pending=participant and exists(db,'reward_receipts')and db.execute('SELECT 1 FROM abyss2026_runs r JOIN reward_receipts p ON r.run=p.run_id WHERE r.account=?AND r.character=?AND r.consumed_proof IS NULL LIMIT 1',(account,character)).fetchone()
        if participant and(refreshed or pending):
            if not recover:return None
            with db:
                db.execute('BEGIN IMMEDIATE');self.guard(s,db);now=int(self.clock());t.recover(account,character,now)
        active,done=self._task_records(t,s,now);row=t.snapshot(account,character)
        try:t.owner(account,character);eligible=True
        except ValueError:eligible=False
        return now,active,done,row,eligible

    def finalize(self,s,replies):
        if self.previous is not None:replies=self.previous.finalize(s,replies)
        if not self.enabled(s)or getattr(s,'reward_transaction',None)is not None:return replies
        restoring=any(e.event_id==0x201 and e.kind in(0x2a,0x2b)for e in replies)
        if s.phase not in('town_ready','dungeon_active')and not restoring:return replies
        now=int(self.clock());account=s.account.account_id;character=s.account.uid
        from els_server.storage.read_scope import snapshot_connection
        with snapshot_connection(s.account.store.path)as db:
            db.execute('BEGIN')
            view=self._current_view(s,db,now,account,character,replies,recover=False)
        if view is None:
            with closing(sqlite3.connect(s.account.store.path,timeout=10))as db:
                view=self._current_view(s,db,now,account,character,replies,recover=True)
        now,active,done,row,eligible=view
        self.observed=(character,week(now));code_rows=dict(self.codes);reward_rows={};out=[];has_reward_table=False
        from els_server.domain.growth_attendance_2026_campaign import reward_rows as decode_rewards
        for event in replies:
            if event.event_id==0x201 and event.kind==0x4b9:code_rows.update(read(event.payload))
            elif event.event_id==0x201 and event.kind==0x4b6:
                has_reward_table=True;reward_rows.update(decode_rewards(event.payload))
            elif event.event_id==0x201 and event.kind==0x2b:
                a,d,tail=split(event.payload);selected=set(rules.quests())
                a=[r for q,r in a if q not in selected]+[r for q,r in active]
                d=[r for q,r in d if q not in selected]+[r for q,r in done]
                out.append(replace(event,payload=bytes(4)+struct.pack('>I',len(a))+b''.join(a)+struct.pack('>I',len(d))+b''.join(d)+tail))
            else:out.append(event)
        # Permanent server calendar; native icon admission is verified separately.
        code_rows[rules.CODE]=CodeEntry(eligible,0,0)
        self.codes=dict(code_rows)
        entries=notice(code_rows)
        reward_rows.update({rid:((t,1,0),)for rid,t in rules.rewards().items()})
        if has_reward_table or restoring:
            payload=struct.pack('>I',len(reward_rows))+b''.join(struct.pack('>iI',rid,len(rows))+b''.join(struct.pack('>iiH',*r)for r in rows)for rid,rows in sorted(reward_rows.items()))
            out.insert(0,Event(0x201,kind=0x4b6,payload=payload))
        signature=(character,wire.state(row).payload,tuple(active),tuple(done),entries.payload)
        if restoring or signature!=self.last:
            out+=[entries,wire.state(row)]
            if not any(e.event_id==0x201 and e.kind==0x2b for e in out):
                for q,record in active:
                    if(character,q,period(q,now))not in self.active_keys:
                        out.append(Event(0x201,kind=0xf0,payload=record+bytes(12)))
            if active:out.append(wire.progress([r for q,r in active]))
        self.active_keys={(character,q,period(q,now))for q,record in active}
        self.last=signature
        return out
