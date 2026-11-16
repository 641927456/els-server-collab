"""Current candidate regression using only owned disposable saves."""
from pathlib import Path
from contextlib import closing
import json,sqlite3,struct,unittest
from unittest.mock import patch
import test_firstbatch as first
import test_secondbatch as second
from els_server.protocol.protocol_codec import Event
from els_server.domain import consumable_flow
from els_server.domain.consumables import ConsumableCoolingDown,require_usable
from els_server.storage.consumables import use
from els_server.storage import pet_support as pet
from els_server.storage.companion_state import handle as companion
from els_server.domain.quick_bindings import item_binding

NOW=first.NOW

class Cooldowns(unittest.TestCase):
    setUp=first.FirstBatch.setUp
    grant=first.FirstBatch.grant
    pet=first.FirstBatch.pet
    unlock=first.FirstBatch.unlock
    count=first.FirstBatch.count
    dump=first.FirstBatch.dump
    session=first.FirstBatch.session
    bind_shortcut=first.FirstBatch.bind_shortcut

    def ready(self):
        active=self.unlock();self.grant((710000,12));binding=item_binding(710000)
        pet.handle(self.path,1001,0x8a1,first.bindings(binding,binding),'bind-both')
        companion(self.path,1001,0x2ec,struct.pack('>Q',active),'summon-owned')
        self.bind_shortcut(710000)

    def test_manual_and_automatic_have_independent_recovery_ledgers(self):
        self.ready();use(self.path,1001,first.drink(),'manual',now=NOW)
        use(self.path,1001,first.drink(),'automatic',now=NOW+1,automatic_use=True)
        self.assertEqual(self.count(710000),10)
        for automatic in (False,True):
            with self.assertRaises(ConsumableCoolingDown):
                use(self.path,1001,first.drink(),'too-soon-'+str(automatic),now=NOW+2,automatic_use=automatic)
        use(self.path,1001,first.drink(),'manual-ready',now=NOW+30)
        use(self.path,1001,first.drink(),'automatic-ready',now=NOW+31,automatic_use=True)
        self.assertEqual(self.count(710000),8)

    def test_automatic_recovery_group_is_shared_across_its_two_slots(self):
        self.ready();use(self.path,1001,first.drink(),'auto-hp',now=NOW,automatic_use=True)
        before=self.dump()
        with self.assertRaises(ConsumableCoolingDown):use(self.path,1001,first.drink(1),'auto-mp',now=NOW+1,automatic_use=True)
        self.assertEqual(before,self.dump())
        use(self.path,1001,first.drink(1),'auto-mp',now=NOW+30,automatic_use=True)
        self.assertEqual(self.count(710000),10)

    def test_automatic_first_does_not_block_manual_and_cold_replay_is_once(self):
        self.ready();use(self.path,1001,first.drink(),'auto-first',now=NOW,automatic_use=True)
        use(self.path,1001,first.drink(),'manual-second',now=NOW+1)
        before=self.dump()
        self.assertEqual(len(use(self.path,1001,first.drink(),'auto-first',now=NOW+2,automatic_use=True)),1)
        self.assertEqual(before,self.dump());self.assertEqual(self.count(710000),10)

    def test_encoding_failure_rolls_back_new_cooldown_schema_and_debit(self):
        self.ready();before=self.dump()
        with patch('els_server.storage.consumables.encode_event',side_effect=ValueError('owned encode failure')):
            with self.assertRaisesRegex(ValueError,'owned encode'):use(self.path,1001,first.drink(),'rollback-auto',now=NOW,automatic_use=True)
        self.assertEqual(before,self.dump())
        use(self.path,1001,first.drink(),'rollback-auto',now=NOW,automatic_use=True)
        self.assertEqual(self.count(710000),11)

    def test_cooling_feedback_is_visible_refusal_without_reapplying_effect(self):
        self.ready();use(self.path,1001,first.drink(),'manual-before',now=NOW)
        use(self.path,1001,first.drink(),'automatic-before',now=NOW,automatic_use=True)
        s=self.session('dungeon_active');before=self.dump()
        with patch('els_server.storage.consumables.time.time',return_value=NOW+1):
            for kind,response in((0x113,0x114),(0x65e,0x65f)):
                events=consumable_flow.handle(s,Event(0x202,kind=kind,payload=first.drink()),401+kind)
                self.assertEqual([e.kind for e in events],[response])
                self.assertEqual(struct.unpack_from('>i',events[0].payload)[0],1369)
        self.assertEqual(before,self.dump())

class Essence(unittest.TestCase):
    setUp=second.SecondBatch.setUp
    dungeon=second.SecondBatch.dungeon

    def test_malformed_and_invalid_phase_requests_have_visible_errors(self):
        for phase in ('town_ready','dungeon_active'):
            self.s.phase=phase
            for raw in (b'',bytes(26),struct.pack('>BBii3f',1,0,0,0,0.,0.,0.)):
                messages=self.s._handle(Event(0x202,kind=0x460,payload=raw,performers=(0,)),701)
                self.assertEqual([e.kind for e in messages],[0x461])
                self.assertEqual(struct.unpack_from('>iI',messages[0].payload),(1836,0))

    def test_wrong_envelope_and_unknown_skill_do_not_mutate_inventory(self):
        self.s.phase='dungeon_active'
        with closing(sqlite3.connect(self.path))as db:before=tuple(db.iterdump())
        raw=struct.pack('>BBii3f',0,0,0,2**31-1,0.,0.,0.)
        for event in (Event(0x202,kind=0x460,payload=raw,performers=(1001,)),Event(0x202,kind=0x460,payload=raw,performers=(0,))):
            reply=self.s._handle(event,702)
            self.assertEqual(struct.unpack_from('>iI',reply[0].payload),(1836,0))
        with closing(sqlite3.connect(self.path))as db:self.assertEqual(before,tuple(db.iterdump()))

class QuestLimits(unittest.TestCase):
    setUp=second.SecondBatch.setUp
    growth_binding=second.SecondBatch.growth_binding
    bind_growth=second.SecondBatch.bind_growth
    seed_completed=second.SecondBatch.seed_completed

    def seed_active(self,count,kind,excluded=()):
        from els_server.domain.seal_quests import quest_catalog
        c=quest_catalog();ids=[q for q,v in sorted(c.quests.items())if v['m_eQuestType']==kind and q not in excluded
            and q not in(25600,25601,25602,25610,25611,25612,45000,26770,52700)][:count]
        self.assertEqual(len(ids),count)
        with closing(sqlite3.connect(self.path))as db,db:
            for qid in ids:
                counts={s['m_iID']:0 for s in c.objectives(qid)}
                db.execute('INSERT OR IGNORE INTO character_quests VALUES(?,?,?,?,?)',(self.a.uid,qid,1799999000,1799999000,json.dumps(counts)))
        return ids

    def test_character_quests_are_accepted_above_fifty_and_cold_restore_keeps_them(self):
        from els_server.storage.seal_quests import QuestState
        from els_server.protocol.quest_messages import initialization
        self.seed_active(55,5,excluded=(26640,26650,26690))
        state=QuestState(self.path,self.a.uid,account_id=1)
        state.action('accept',dict(quest=26640,npc=10025),'owned-above-fifty',lambda r:[],now=1800000000,location=('town',20013))
        self.assertEqual(len(QuestState(self.path,self.a.uid,account_id=1).snapshot()['active']),56)
        initialization(state.snapshot())
        before=state.snapshot()
        state.action('accept',dict(quest=26640,npc=10025),'owned-above-fifty',lambda r:[],now=1800000001,location=('town',20013))
        self.assertEqual(before,state.snapshot())

    def test_side_quest_twenty_is_separate_from_character_quests(self):
        from els_server.domain.seal_quests import quest_catalog,acceptance_available
        c=quest_catalog();main=[dict(id=q)for q in self.seed_active(55,5)]
        side=[dict(id=q)for q,v in c.quests.items()if v['m_eQuestType']==0][:20]
        self.assertTrue(acceptance_available(c.quest(side[-1]['id']),main+side[:19]))
        self.assertFalse(acceptance_available(c.quest(side[-1]['id']),main+side))
        self.assertTrue(acceptance_available(c.quest(26640),main+side))

    def test_bound_growth_region_preview_and_writer_continue_above_fifty(self):
        from els_server.domain.boosting_2026_region_entries import resume,ENTRIES
        self.seed_active(55,5,excluded=ENTRIES);self.seed_completed(26640,26650,26680)
        binding=self.growth_binding();self.bind_growth(binding)
        self.assertTrue(binding._automatic_work(self.s,'region'))
        messages=binding._resume_region_entries(self.s,[])
        self.assertEqual([struct.unpack_from('>i',e.payload)[0]for e in messages],[26690])
        self.assertEqual(binding._resume_region_entries(self.s,[]),[])

    def test_epic_after_reward_is_not_blocked_by_unrelated_task_count(self):
        from els_server.storage.epic_followups import accept_after_reward
        from els_server.storage.seal_quests import load_character
        from els_server.storage.inventory_state import load_items
        self.seed_active(55,5,excluded=(26640,26650));self.seed_completed(26640)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            character=load_character(db,self.a.uid,1)
            accepted=accept_after_reward(db,self.a.uid,26640,character,load_items(db,self.a.uid),('town',20013),1800000000)
            self.assertEqual(accepted,(26650,))

    def test_actual_side_writer_accepts_twentieth_and_refuses_twenty_first(self):
        from els_server.domain.seal_quests import quest_catalog,require_eligible
        from els_server.storage.seal_quests import QuestState,load_character,completed_ids
        from els_server.storage.inventory_state import load_items
        c=quest_catalog();candidates=[]
        with closing(sqlite3.connect(self.path))as db:
            character=load_character(db,self.a.uid,1);items=load_items(db,self.a.uid);done=completed_ids(db,self.a.uid)
        for qid,q in sorted(c.quests.items()):
            if q['m_eQuestType']!=0 or qid in(35630,52700,26770):continue
            try:require_eligible(character,q,done,items,location=('town',20000))
            except ValueError:continue
            candidates.append(qid)
        self.assertGreaterEqual(len(candidates),2)
        self.seed_active(55,5);self.seed_active(19,0,excluded=candidates)
        state=QuestState(self.path,self.a.uid,account_id=1)
        state.action('accept',dict(quest=candidates[0],npc=10025),'side-twentieth',lambda r:[],now=1800000000)
        before=state.snapshot()
        self.assertEqual(sum(c.quest(v['id'])['m_eQuestType']in(0,1)for v in before['active']),20)
        with self.assertRaisesRegex(ValueError,'Side quest capacity'):
            state.action('accept',dict(quest=candidates[1],npc=10025),'side-twenty-first',lambda r:[],now=1800000001)
        self.assertEqual(before,state.snapshot())

    def test_quick_start_uses_side_budget_and_keeps_character_tasks(self):
        from els_server.storage.quick_start import ensure,accept_next
        from els_server.domain.quick_start import QUESTS
        from els_server.domain.seal_quests import quest_catalog
        c=quest_catalog();self.assertTrue(all(c.quest(q)['m_eQuestType']==1 for q in QUESTS))
        self.seed_active(55,5);self.seed_active(19,0)
        with closing(sqlite3.connect(self.path))as db,db:
            ensure(db);db.execute('INSERT INTO quick_start_accounts VALUES(?,?,?)',(1,self.a.uid,1800000000))
            self.assertEqual(accept_next(db,self.a.uid,1800000000),(QUESTS[0],))
            self.assertEqual(accept_next(db,self.a.uid,1800000001),())
            db.execute('DELETE FROM character_quests WHERE owner=? AND quest=?',(self.a.uid,QUESTS[0]))
            extra=next(q for q,v in c.quests.items()if v['m_eQuestType']==0 and not db.execute('SELECT 1 FROM character_quests WHERE owner=? AND quest=?',(self.a.uid,q)).fetchone())
            db.execute('INSERT INTO character_quests VALUES(?,?,?,?,?)',(self.a.uid,extra,1,1,'{}'))
            with self.assertRaisesRegex(ValueError,'Side quest capacity'):accept_next(db,self.a.uid,1800000002)

class Reselection(unittest.TestCase):
    setUp=second.SecondBatch.setUp

    def character(self,*,level=20,cls=10):
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE characters SET unit_class=?,level=? WHERE uid=?',(cls,level,self.a.uid))
        return self.a.character()

    def dump(self):
        with closing(sqlite3.connect(self.path))as db:return tuple(db.iterdump())

    def quest(self):
        from els_server.storage.seal_quests import QuestState
        from els_server.domain.reselection_quest import catalog
        self.character();state=QuestState(self.path,self.a.uid,account_id=1)
        q=catalog()['quests']['39480']
        state.action('accept',dict(quest=39480,npc=10025),'reselect-accept',lambda r:[],now=1800000000)
        for n in range(2):state.record('reselect-clear:'+str(n),dict(kind='clear',dungeon=30100,level=20,rank=5),b'owned-real-clear-proof')
        result=state.action('claim',dict(quest=39480,npc=10025,choices=()),'reselect-claim',lambda r:[],now=1800000010)
        return state,result

    def ticket(self):
        self.character()
        from els_server.storage.inventory_state import grant_items
        from els_server.domain.reward_rules import item_plan
        with closing(sqlite3.connect(self.path))as db,db:
            return grant_items(db,[dict(item_plan(135872,1),expires_at=1800086410)],self.a.uid)[0]

    def request(self,item,chosen=11):
        return Event(0x202,kind=0x219,payload=struct.pack('>QQiiIB',item['uid'],0,chosen,0,0,0))

    def test_real_task_clear_claim_grants_both_original_timed_rewards_once(self):
        state,result=self.quest()
        items=self.a.get_inventory_snapshot()['items']
        rewards=[i for i in items if i['template']in(135871,135872)]
        self.assertEqual({i['template']for i in rewards},{135871,135872})
        self.assertEqual({i['expires_at']for i in rewards},{1800086410})
        before=self.dump()
        state.action('claim',dict(quest=39480,npc=10025,choices=()),'reselect-claim',lambda r:[],now=1800000011)
        self.assertEqual(before,self.dump())
        with self.assertRaisesRegex(ValueError,'already rewarded'):
            state.action('accept',dict(quest=39480,npc=10025),'second-reselect',lambda r:[],now=1800000012)
        self.assertEqual(before,self.dump())
        ticket=next(i for i in rewards if i['template']==135872)
        messages=self.s._handle(self.request(ticket),810)
        self.assertEqual(struct.unpack_from('>i',messages[0].payload)[0],0)
        self.assertEqual(self.a.character()['unit_class'],11)

    def test_selected_ticket_changes_career_and_cold_replay_does_not_reconsume(self):
        item=self.ticket();event=self.request(item)
        from els_server.domain.skill_rules import equippable_skills
        from els_server.domain.character_rules import default_slots
        old_character=self.a.character();old_skills=set(equippable_skills(old_character))
        target_skills=set(equippable_skills(dict(old_character,unit_class=11)))
        exclusive=next(iter(sorted(old_skills-target_skills)))
        slots=list(default_slots(old_character));slots[0]=exclusive
        self.assertEqual(len([v for v in slots if v]),len({v for v in slots if v}))
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('INSERT INTO skill_slots VALUES(?,?,?) ON CONFLICT(uid) DO UPDATE SET payload=excluded.payload',(self.a.uid,struct.pack('>22i',*slots),1))
        messages=self.s.handle(event,811)
        self.assertEqual(struct.unpack_from('>i',next(m for m in messages if m.kind==0x21a).payload)[0],0)
        self.assertIn(0x29f,[m.kind for m in messages]);self.assertEqual(self.a.character()['unit_class'],11)
        with closing(sqlite3.connect(self.path))as db:
            cold_slots=struct.unpack('>22i',db.execute('SELECT payload FROM skill_slots WHERE uid=?',(self.a.uid,)).fetchone()[0])
        self.assertNotIn(exclusive,cold_slots);self.assertTrue({v for v in cold_slots if v}<=target_skills)
        self.assertFalse(any(i['uid']==item['uid']for i in self.a.get_inventory_snapshot()['items']))
        before=self.dump();again=self.s.handle(event,811)
        self.assertEqual(struct.unpack_from('>i',next(m for m in again if m.kind==0x21a).payload)[0],0)
        self.assertNotIn(0x29f,[m.kind for m in again]);self.assertEqual(before,self.dump())

    def test_wrong_stage_level_target_and_expiry_are_real_refusals(self):
        item=self.ticket()
        for level,cls,chosen in((20,1,11),(35,100,11),(20,10,10),(20,10,12),(20,10,100),(20,10,2147483647)):
            with self.subTest(level=level,cls=cls,chosen=chosen):
                self.character(level=level,cls=cls);before=self.dump()
                messages=self.s._handle(self.request(item,chosen),812)
                self.assertEqual(struct.unpack_from('>i',messages[0].payload)[0],1836)
                self.assertEqual(before,self.dump())
        self.character()
        with patch('els_server.domain.item_expiration.time.time',return_value=1800086411):
            before=self.dump();messages=self.s._handle(self.request(item),813)
        self.assertEqual(struct.unpack_from('>i',messages[0].payload)[0],1836)
        self.assertEqual(before,self.dump())
        from els_server.storage.careers import use_career_item
        def owner_rejected(db):raise ValueError('owned lease changed')
        with self.assertRaisesRegex(ValueError,'owned lease changed'):
            use_career_item(self.path,self.a.uid,self.request(item).payload,'lease-failure',selected=True,prepare=owner_rejected)
        self.assertEqual(before,self.dump())

    def test_encoding_failure_and_owner_change_roll_back_ticket_and_career(self):
        item=self.ticket();before=self.dump()
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=ValueError('owned encode failure')):
            messages=self.s._handle(self.request(item),814)
        self.assertEqual(struct.unpack_from('>i',messages[0].payload)[0],1836)
        self.assertEqual(before,self.dump())

    def test_fixed_career_book_keeps_original_empty_selection_and_advancement(self):
        from els_server.storage.careers import use_career_item
        from els_server.storage.inventory_state import grant_items
        from els_server.domain.reward_rules import item_plan
        from els_server.protocol.career_messages import use_request
        self.character(level=20,cls=1)
        with closing(sqlite3.connect(self.path))as db,db:
            item=grant_items(db,[item_plan(214410,1)],self.a.uid)[0]
        raw=struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)
        self.assertEqual(use_request(raw),item['uid'])
        with self.assertRaises(ValueError):use_request(self.request(item).payload)
        result=use_career_item(self.path,self.a.uid,raw,'fixed-career-unchanged')
        self.assertEqual(result['after']['unit_class'],10)
        before=self.dump();self.assertTrue(use_career_item(self.path,self.a.uid,raw,'fixed-career-unchanged')['replayed'])
        self.assertEqual(before,self.dump())

    def test_acceptance_level_limit_is_distinct_from_existing_ticket_use(self):
        from els_server.storage.seal_quests import QuestState
        item=self.ticket();self.character(level=35,cls=10);before=self.dump()
        with self.assertRaisesRegex(ValueError,'Quest level requirement'):
            QuestState(self.path,self.a.uid,account_id=1).action('accept',dict(quest=39480,npc=10025),'too-late-quest',lambda r:[],now=1800000000)
        self.assertEqual(before,self.dump())
        reply=self.s._handle(self.request(item),815)
        self.assertEqual(struct.unpack_from('>i',reply[0].payload)[0],0)
        self.assertEqual(self.a.character()['unit_class'],11)

    def test_ticket_lock_and_lost_actor_after_encoding_preserve_the_save(self):
        from els_server.storage.item_locks import assign
        item=self.ticket()
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');assign(db,self.a.uid,item['uid'],1800000000)
        before=self.dump();reply=self.s._handle(self.request(item),816)
        self.assertEqual(struct.unpack_from('>i',reply[0].payload)[0],1836);self.assertEqual(before,self.dump())
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE item_locks SET lock_until=1 WHERE item_uid=?',(item['uid'],))
        from els_server.protocol.protocol_codec import encode_event as original_encode
        def changed_actor(event):
            result=original_encode(event);self.s.phase='town_loading';return result
        before=self.dump()
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=changed_actor):reply=self.s._handle(self.request(item),817)
        self.assertEqual(struct.unpack_from('>i',reply[0].payload)[0],1836);self.assertEqual(before,self.dump())
        self.s.phase='town_ready';reply=self.s._handle(self.request(item),818)
        self.assertEqual(struct.unpack_from('>i',reply[0].payload)[0],0)
        with closing(sqlite3.connect(self.path))as db:
            self.assertEqual(db.execute('SELECT * FROM item_locks WHERE item_uid=?',(item['uid'],)).fetchall(),[])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
