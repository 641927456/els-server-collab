"""Explicitly injected local candidate: authenticated EE/F4 and mixed restore.

This does not implement the unresolved8173 join. The schedule predicate and
clock are server-owned injection, never values from a client packet.
"""
from contextlib import closing
from functools import wraps
import logging
from pathlib import Path
import hashlib,json,sqlite3,struct
from els_server.protocol import quest_messages as ordinary
from els_server.protocol import boosting_2026_quest as wire
from els_server.protocol.boosting_2026_restore import merge
from els_server.protocol.protocol_codec import Event
from els_server.storage.boosting_2026_first_rewards import FirstRewards
from els_server.storage.inventory_state import InventoryFull,load_items
from els_server.storage.seal_quests import load_character,current_slots
from els_server.storage.reward_state import validate_balances
from els_server.domain.seal_quests import require_eligible
from els_server.domain.boosting_2026 import BoostingDefinition


def defer_automatic_lock(empty):
    """Only automatic work can wait for a later normal finalize/reconnect.

    Never applied to run admission, claims, or explicit task acceptance.
    Rollback/close has completed before the exception reaches this boundary.
    """
    def decorate(method):
        @wraps(method)
        def call(*args,**kwargs):
            try:return method(*args,**kwargs)
            except sqlite3.OperationalError as error:
                code=getattr(error,'sqlite_errorcode',None)
                if type(code) is not int or code & 255 not in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED):raise
                logging.getLogger(__name__).warning('Deferred automatic growth %s after SQLite lock code=%s',method.__name__,code,exc_info=True)
                return empty()
        return call
    return decorate


class BoostingQuestBinding:
    def __init__(self,original,*,clock,campaign_open):
        self.definition=BoostingDefinition.from_original(original)
        self.original=original;self.clock=clock;self.campaign_open=campaign_open
        self.quests={r['definition']['m_iID']:r['definition'] for r in json.loads(original)['quests']}

    @staticmethod
    def enabled(s):
        return (s.role=='game' and s.client_build=='dx11_260923' and s.item_test
                and s.account.characters is not None and s.account.store is not None
                and not getattr(s,'released',False))

    def _store(self,db):return FirstRewards(db,self.original)

    def _participant(self,db,s):
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='boosting2026_participation'").fetchone():return False
        # Eligibility does not need construction/validation of reward profiles.
        from els_server.storage.boosting_2026_participation import BoostingParticipation
        participation=BoostingParticipation(db,self.original)
        level=participation._owner_level(s.account.account_id,s.account.uid)
        bound=participation._read(s.account.account_id)
        return level==99 and bound is not None and bound.character_uid==s.account.uid

    def _read_participant(self,s):
        """Read-only exclusion before acquiring any automatic growth writer.

        A positive preview never authorizes mutation: each existing write
        transaction still rechecks ownership, level and the saved binding.
        Do not cache a negative preview across a normal join or character swap.
        """
        with snapshot_connection(s.account.store.path) as db:
            db.execute('BEGIN')
            return self._participant(db,s)

    def _automatic_work(self,s,kind):
        """A read preview can exclude work; positive results never authorize it."""
        with snapshot_connection(s.account.store.path) as db:
            db.execute('BEGIN')
            if not self._participant(db,s):return False
            t=self._store(db);account=s.account.account_id;uid=s.account.uid
            active=t.snapshot(account=account,character=uid)
            if kind=='enroll':
                if active is not None:return False
                return self.definition.next_task(level=99,character_uid=uid,bound_character_uid=uid,
                    completed=t._completed(account,uid)) is not None
            if kind=='recover':
                if active is None:return False
                task=self.definition.task(active['id'])
                if task.condition_kind!=8 or active['count']==task.required_count:return False
                return db.execute('''SELECT 1 FROM boosting2026_task_runs r JOIN reward_receipts p ON p.run_id=r.run
                    WHERE r.account=? AND r.character=? AND r.quest=? AND r.accepted_at=?
                    AND r.consumed_proof IS NULL LIMIT 1''',(account,uid,active['id'],active['accepted_at'])).fetchone() is not None
            if kind=='receipts':
                return db.execute('''SELECT 1 FROM boosting2026_task_runs r JOIN reward_receipts p ON p.run_id=r.run
                    WHERE r.account=? AND r.character=? AND r.consumed_proof IS NULL LIMIT 1''',(account,uid)).fetchone() is not None
            if kind=='region':
                from els_server.domain.boosting_2026_region_entries import ENTRIES
                from els_server.domain.region_quests import region_catalog
                from els_server.storage.seal_quests import completed_ids
                if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_quests'").fetchone():return True
                done=completed_ids(db,uid)
                current={q for q, in db.execute('SELECT quest FROM character_quests WHERE owner=?',(uid,))}
                if len(current)>=30:return False
                pending=[q for q in ENTRIES if q not in current and q not in done]
                if not pending:return False
                character=load_character(db,uid,account);items=load_items(db,uid);catalog=region_catalog()
                for qid in pending:
                    q=catalog.data['quests'][str(qid)]['definition']
                    if q['m_eQuestType']!=5 or q['m_bRepeat'] or q['m_bIsTimeEvent']:raise ValueError('Region entry source changed')
                    try:require_eligible(character,q,done,items,location=('town',s.account.get_location()['map']))
                    except ValueError:continue
                    return True
                return False
            raise ValueError('Unknown automatic growth work')

    def _view(self,db,s):
        if not self._participant(db,s):return None,[]
        t=self._store(db);active=t.snapshot(account=s.account.account_id,character=s.account.uid)
        ids=t._completed(s.account.account_id,s.account.uid)
        completed=[dict(id=q,completed_at=at) for q,at in db.execute('SELECT quest,claimed_at FROM boosting2026_task_rewards WHERE account=? ORDER BY quest',(s.account.account_id,))]
        if tuple(r['id'] for r in completed)!=ids:raise ValueError('Growth history changed')
        return active,completed

    def handle(self,s,event,sequence):
        if (event.event_id!=0x202 or event.kind not in (0xee,0xfa,0xf4) or len(event.payload)<4
                or not 169500<=struct.unpack_from('>i',event.payload)[0]<=169519 or not self.enabled(s)):
            return None
        qid=struct.unpack_from('>i',event.payload)[0]
        def failure(result=ordinary.QUEST_REWARD_UNAVAILABLE):
            if event.kind==0xee:return [ordinary.accept_ack(-1)]
            if event.kind==0xfa:
                from els_server.domain.quest_flow import initialization
                return [initialization(s)]
            inv=s.account.get_inventory_snapshot()
            return [ordinary.reward_ack(qid,s.account.character(),s.account.get_location(),s.account.get_skills(),inv['balances'],inv['items'],result=result)]
        if (s.phase!='town_ready' or type(sequence) is not int or not 1<=sequence<2**32
                or event.performers!=(0,) or event.uid!=0xffffffffffffffff
                or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):return failure()
        try:
            request=ordinary.request(event.kind,event.payload)
            if event.kind==0xfa:return failure() # original abandon behavior unresolved
            now=self.clock();open_now=self.campaign_open(s,now)
            q=self.quests[qid]
            allowed=(q['m_eStartNPCID'],10025) if event.kind==0xee else (0,q['m_eEndNPCID'],10025)
            if request['npc'] not in allowed:raise ValueError('Growth original NPC context mismatch')
            with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
                with write_transaction(db):
                    t=self._store(db)
                    if not self._participant(db,s):raise ValueError('No eligible growth participant')
                    character=load_character(db,s.account.uid,s.account.account_id)
                    require_eligible(character,q,t._completed(s.account.account_id,s.account.uid),load_items(db,s.account.uid),location=('town',s.account.get_location()['map']))
                    if event.kind==0xee:
                        active=t.accept_next(account=s.account.account_id,character=s.account.uid,quest=qid,accepted_at=now,campaign_open=open_now)
                        answer=[ordinary.accept_ack(),wire.accepted(self.definition,active,owner_uid=s.account.uid)]
                    else:
                        active=t.snapshot(account=s.account.account_id,character=s.account.uid)
                        if qid not in t._completed(s.account.account_id,s.account.uid) and (active is None or active['id']!=qid or active['count']<self.definition.task(qid).required_count):
                            db.rollback();return failure(ordinary.QUEST_REQUIREMENTS_NOT_MET)
                        balances=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(s.account.uid,)).fetchone())
                        slots=current_slots(db,character);location=s.account.get_location()
                        def encode(r):
                            return ordinary.reward_ack(qid,character,location,slots,balances,r['items'],r['updates'],replayed=r['replayed'],completed_at=r['completed_at']).payload
                        r=t.claim(account=s.account.account_id,character=s.account.uid,quest=qid,claimed_at=now,campaign_open=open_now,encode=encode)
                        answer=[Event(0x201,kind=0xf5,payload=r['response'])]
            # Only committed state is sent. The session finalizers append both
            # attendance and growth records to this ordinary replacement map.
            if event.kind==0xf4:
                from els_server.domain.quest_flow import initialization
                answer.append(initialization(s))
            return answer
        except InventoryFull:return failure(ordinary.QUEST_REWARD_BAG_FULL)
        except ValueError:return failure()

    def capture(self,s):
        """Called at the authenticated loading100 transition, before play."""
        if not self.enabled(s) or s.dungeon_run is None or not s.reward_test:return
        run=s.dungeon_run
        # Cooperative runs have a shared run UUID and per-player reward UUIDs.
        # That lifecycle has its own dispatcher; do not disrupt it or attach
        # this solo bridge retrospectively to a different reward identity.
        if run.run_id!=s.reward_run_id:return
        if not self._read_participant(s):return
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
            with write_transaction(db):
                if self._participant(db,s):self._store(db).admit_run(account=s.account.account_id,character=s.account.uid,run_id=run.run_id,dungeon=run.identity)

    @defer_automatic_lock(list)
    def observe_clear(self,s):
        run=s.dungeon_run
        if run is None or not s.reward_test or not s.clear_notified or s.reward_receipt is None:return []
        if run.run_id!=s.reward_run_id or s.reward_receipt.get('run_id')!=run.run_id:return []
        # Same authoritative static-clear proof as dungeon_flow.clear, including
        # source digest and server-accepted death payloads; no client counters.
        deaths=hashlib.sha256()
        for key,value in sorted(run.defeated.items()):deaths.update(struct.pack('>iI',key,len(value))+value)
        proof=(b'local-static-clear-v2'+struct.pack('>Qiii',s.account.uid,run.identity,run.stage,run.part)
               +bytes.fromhex(run.graph['source_sha256'])+deaths.digest())
        if not self._read_participant(s):return []
        # A repeated clear still validates its durable proof, but a consumed
        # record needs no writer. Missing admission never gets created here.
        with snapshot_connection(s.account.store.path) as db:
            db.execute('BEGIN')
            if not self._participant(db,s):return []
            saved=db.execute('SELECT consumed_proof FROM boosting2026_task_runs WHERE run=?',(run.run_id,)).fetchone()
            if saved is None:return []
            if saved[0] is not None:
                row=self._store(db).observe_clear(account=s.account.account_id,character=s.account.uid,run_id=run.run_id,proof=proof)
                if row is not None:raise ValueError('Consumed growth run changed on read')
                return []
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
            with write_transaction(db):
                if not self._participant(db,s):return []
                # No retrospective run admission, including after attaching this
                # candidate to an already running session.
                if not db.execute('SELECT 1 FROM boosting2026_task_runs WHERE run=?',(run.run_id,)).fetchone():return []
                row=self._store(db).observe_clear(account=s.account.account_id,character=s.account.uid,run_id=run.run_id,proof=proof)
                messages=[wire.progress(self.definition,row,owner_uid=s.account.uid)] if row else []
        return messages

    @defer_automatic_lock(list)
    def recover_committed(self,s):
        """Restore only admitted authoritative receipts, independent of live run memory."""
        if not self._automatic_work(s,'receipts'):return []
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
            with write_transaction(db):
                if not self._participant(db,s):return []
                rows=self._store(db).recover_committed(account=s.account.account_id,character=s.account.uid)
                return [wire.progress(self.definition,rows[-1],owner_uid=s.account.uid)] if rows else []

    @defer_automatic_lock(lambda:None)
    def _enroll_next(self,s):
        """Server event activation, not a client-selected or retroactive clear.

        Compatibility scheduling: the original window offers no accept button.
        Reuses the legacy time-event auto-accept/after-quest flow, current20
        definitions and current F0/2B. Not a claim of recovered2026 server code.
        """
        if s.phase!='town_ready':return None
        now=self.clock()
        if not self.campaign_open(s,now):return None
        if not self._automatic_work(s,'enroll'):return None
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
            with write_transaction(db):
                if not self._participant(db,s):return None
                t=self._store(db)
                if t.snapshot(account=s.account.account_id,character=s.account.uid) is not None:return None
                done=t._completed(s.account.account_id,s.account.uid)
                task=self.definition.next_task(level=99,character_uid=s.account.uid,
                    bound_character_uid=s.account.uid,completed=done)
                if task is None:return None
                q=self.quests[task.quest_id]
                character=load_character(db,s.account.uid,s.account.account_id)
                require_eligible(character,q,done,load_items(db,s.account.uid),
                    location=('town',s.account.get_location()['map']))
                row=t.accept_next(account=s.account.account_id,character=s.account.uid,
                    quest=task.quest_id,accepted_at=now,campaign_open=True)
                message=wire.accepted(self.definition,row,owner_uid=s.account.uid)
                from els_server.protocol.protocol_codec import encode_event
                encode_event(message) # No persisted task if its original message cannot encode.
        return message

    @defer_automatic_lock(list)
    def _resume_region_entries(self,s,replies):
        """Scoped compatibility scheduling for this selected growth participant.

        Reuses legacy epic auto-enrollment and current region definitions.
        No completed quest, clear credit, admission bypass or award is added.
        Root26640 at eligible99 is local compatibility scheduling, not a
        claim of recovered2026 original server enrollment timing.
        """
        if s.phase!='town_ready' or not self.campaign_open(s,self.clock()):return []
        owner=(str(s.account.store.path),s.account.uid)
        refresh=any(e.event_id==0x201 and e.kind==0xf5 and len(e.payload)>=4
                    and struct.unpack_from('>i',e.payload)[0]==0 for e in replies)
        if getattr(self,'_region_entry_owner',None)==owner and not refresh:return []
        from els_server.domain.boosting_2026_region_entries import resume
        from els_server.protocol.protocol_codec import encode_event
        if not self._automatic_work(s,'region'):return []
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
            with write_transaction(db):
                if not self._participant(db,s):return []
                messages=resume(db,s.account.uid,s.account.account_id,now=self.clock(),
                    location=('town',s.account.get_location()['map']))
                for message in messages:encode_event(message)
        self._region_entry_owner=owner
        return messages

    def refresh_for_window(self,s):
        """F0 is consumed while the growth window's D2A is outstanding.

        The original client does not read a late2B here. Emit at most one F0
        for each accepted generation on this connection, using current state.
        No client input, objective count or reward is manufactured.
        """
        if not self.enabled(s) or s.phase!='town_ready':return []
        self._enroll_next(s)
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
            db.execute('BEGIN');active,completed=self._view(db,s)
        if active is None:return []
        signature=(s.account.uid,active['id'],active['accepted_at'])
        if getattr(self,'_window_quest_signature',None)==signature:return []
        message=wire.accepted(self.definition,active,owner_uid=s.account.uid)
        from els_server.protocol.protocol_codec import encode_event
        encode_event(message)
        self._window_quest_signature=signature
        return [message]

    def finalize(self,s,replies):
        if not self.enabled(s):return replies
        if s.phase not in ('town_ready','dungeon_active') and not any(e.event_id==0x201 and e.kind==0x2b for e in replies):return replies
        out=list(replies)
        out+=self._resume_region_entries(s,replies)
        if any(e.event_id==0x201 and e.kind==0xf5 and len(e.payload)>=8
               and struct.unpack_from('>i',e.payload)[0]==0
               and 169500<=struct.unpack_from('>i',e.payload,4)[0]<=169519 for e in replies):
            out+=self.refresh_for_window(s)
        out+=self.recover_committed(s)
        if s.phase in ('town_ready','dungeon_active'):out+=self.observe_clear(s)
        with closing(sqlite3.connect(s.account.store.path,timeout=10)) as db:
            db.execute('BEGIN');active,completed=self._view(db,s)
        return [merge(e,self.definition,active,completed,owner_uid=s.account.uid) for e in out]

from els_server.storage.sqlite_timing import write_transaction

from els_server.storage.read_scope import snapshot_connection
