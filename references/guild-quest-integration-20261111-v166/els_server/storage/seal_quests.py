"""Atomic quest state, progress evidence, inventory consumption and rewards."""
from contextlib import closing,contextmanager
from pathlib import Path
from els_server.storage.read_scope import canonical_path
import hashlib,json,sqlite3,struct,time,functools
from els_server.domain.seal_quests import quest_catalog,sequence,require_eligible,target,objective_increment,acceptance_available
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage import periodic_quest_scope as erp_scope
from els_server.storage.erp_support_quest_scope import _table_snapshot


SAVED_OBJECTIVE_KINDS=frozenset((3,31,38,70,80,81,110,121))


@functools.lru_cache(maxsize=1)
def collection_quest_ids():
    catalog=quest_catalog()
    return frozenset(q for q in catalog.quests if any(sub['m_eClearType'] in SAVED_OBJECTIVE_KINDS for sub in catalog.objectives(q)))


@contextmanager
def _progress_connection(path,transaction):
    """Own one writer normally; a shared caller owns its exact active writer."""
    if transaction is None:
        with closing(sqlite3.connect(path,timeout=10)) as db:
            with write_transaction(db):
                yield db
        return
    if not isinstance(transaction,sqlite3.Connection) or not transaction.in_transaction:
        raise ValueError('Quest shared progress requires an active transaction')
    attached=transaction.execute('PRAGMA database_list').fetchall()
    main=[row[2] for row in attached if row[1]=='main']
    if (len(main)!=1 or not main[0] or canonical_path(main[0])!=canonical_path(path)
            or any(row[1] not in ('main','temp') for row in attached)):
        raise ValueError('Quest shared progress database mismatch')
    yield transaction
    if not transaction.in_transaction:
        raise ValueError('Quest shared progress transaction ended')


class QuestIncomplete(ValueError):
    """An accepted task still lacks an objective or collection requirement."""

def progress_proof(owner,event_id,proof):
    """Independent accepted deaths may contain identical native payloads."""
    return hashlib.sha256(b'quest-event-v1\0'+struct.pack('>Q',owner)+event_id.encode('utf8')+b'\0'+proof).digest()

def ensure(db):
    from els_server.storage.ep_points import ensure as ensure_ep
    ensure_ep(db)
    db.execute('CREATE TABLE IF NOT EXISTS character_quests (owner INTEGER NOT NULL REFERENCES characters(uid), quest INTEGER NOT NULL, accepted_at INTEGER NOT NULL, generation INTEGER NOT NULL, objectives TEXT NOT NULL, PRIMARY KEY(owner,quest))')
    db.execute('CREATE TABLE IF NOT EXISTS completed_quests (owner INTEGER NOT NULL REFERENCES characters(uid), quest INTEGER NOT NULL, completed_at INTEGER NOT NULL, reward_json TEXT NOT NULL, PRIMARY KEY(owner,quest))')
    db.execute('CREATE TABLE IF NOT EXISTS quest_actions (operation_id TEXT PRIMARY KEY, owner INTEGER NOT NULL, kind TEXT NOT NULL, request_hash TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS quest_progress_events (owner INTEGER NOT NULL, event_id TEXT NOT NULL, proof_hash TEXT NOT NULL, event_json TEXT NOT NULL, PRIMARY KEY(owner,event_id))')

def completed_ids(db,uid):
    character_uid(uid)
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='completed_quests'").fetchone():return frozenset()
    return frozenset(r[0] for r in erp_scope.completed_rows(db,uid))

def load_character(db,uid,account_id=None,*,identity_only=False):
    from els_server.storage.characters import Characters
    from els_server.storage.skill_unlocks import saved_groups
    from els_server.storage.skill_expansion import is_expanded
    from els_server.storage.bag_capacity import saved_capacities
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_owners'").fetchone():raise ValueError('Quest character owner mapping required')
    saved=db.execute('SELECT c.uid,name,unit_type,unit_class,level,transcendence,master,revision,o.account_id FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=?',(uid,)).fetchone()
    if saved is None:raise ValueError('Unknown owned quest character')
    owner=saved[-1]
    if type(owner)is not int or not 1<=owner<2**63 or account_id is not None and(type(account_id)is not int or account_id!=owner):raise ValueError('Quest character owner mismatch')
    row=dict(Characters._row(saved[:-1]),account_id=owner)
    if identity_only:return row
    if row['unit_type']==10:
        from els_server.storage.luciel_state import state,active_state
        row['luciel_style']=state(db,uid)['style']
        row['luciel_active_unit']=active_state(db,uid)['active_unit']
    from els_server.storage.achievements import statuses as achievement_statuses
    row['achievement_status']=achievement_statuses(db,owner,(uid,))[uid]
    from els_server.storage.quick_start import participant as quick_start_participant
    row['quick_start']=quick_start_participant(db,uid,owner)
    a=db.execute('SELECT template,evolution,level,experience,potentials FROM character_artifacts WHERE uid=?',(uid,)).fetchone()
    row['artifact']=dict(template=a[0],evolution=a[1],level=a[2],experience=a[3],potentials=json.loads(a[4])) if a else None
    from els_server.storage.ep_points import balance as ep_balance
    ep=ep_balance(db,uid)
    if ep:row['ep']=ep
    from els_server.storage.pvp_official_profiles import wallet
    row['ap'],row['pvp_rank']=wallet(db,uid,owner)
    from els_server.storage.life_stamina import snapshot as life_snapshot
    from els_server.storage.bank_state import account_for
    row['life_stamina']=life_snapshot(db,uid,account_id if account_id is not None else account_for(db,uid))
    row['skill_seal_groups']=saved_groups(db,uid);row['skill_row_expanded']=is_expanded(db,uid);row['bag_capacities']=saved_capacities(db,uid)
    # F5 embeds the same full-unit fields as login/D9. Read current saved
    # state inside this writer, so a quest reward cannot send fixture zeros
    # for the owner's existing profession or account resonance.
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_owners'").fetchone():
        saved_owner=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()
        if saved_owner is not None:
            if saved_owner!=(row['account_id'],):raise ValueError('Quest character owner changed during projection')
            from els_server.storage.resonance_state import snapshot as resonance_snapshot
            from els_server.storage.character_projection import skill_trait_fields,skill_page_fields,force_fields,cleared_dungeons,profession_fields
            # Full-unit refreshes retain the same current native combat inputs as login.
            from els_server.storage.titles import equipped as equipped_title,completed_for_equipment
            row['title']=equipped_title(db,uid);row['title_completed_quests']=completed_for_equipment(db,uid)
            row.update(skill_trait_fields(db,row,include_empty=True))
            row.update(skill_page_fields(db,uid,include_single=True))
            row.update(force_fields(db,uid))
            has_records=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dungeon_records'").fetchone() is not None
            row['cleared_dungeons']=cleared_dungeons(db,uid,has_records=has_records)
            row['resonance']=resonance_snapshot(db,uid,saved_owner[0])
            from els_server.domain.normal_fatigue_rules import enabled as normal_fatigue_enabled
            if normal_fatigue_enabled():
                from els_server.storage.normal_fatigue import snapshot as normal_fatigue_snapshot
                row['normal_fatigue']=normal_fatigue_snapshot(db,uid,saved_owner[0])
            from els_server.storage.guild_membership_state import snapshot as guild_snapshot
            row['guild_membership']=guild_snapshot(db,uid,saved_owner[0])
            from els_server.storage.el_search_collection import snapshot as collection_snapshot
            collection=collection_snapshot(db,uid,saved_owner[0])
            if collection is not None:row['el_search_collection']=collection
            row.update(profession_fields(db,uid,saved_owner[0]))
    return row

def current_slots(db,character):
    from els_server.domain.skill_rules import upgraded_slots
    from els_server.domain.character_rules import default_slots
    row=db.execute('SELECT payload FROM skill_slots WHERE uid=?',(character['uid'],)).fetchone()
    return upgraded_slots(struct.unpack('>22i',row[0]),character) if row else default_slots(character)

def _inventory_count(items,template,*,quest=None):
    from els_server.domain.item_expiration import expired
    from els_server.domain.item_locks import locked
    return sum(i['count'] for i in items if i['template']==template and i['group']!=9 and not expired(i) and not locked(i) and (quest!=25600 or i['group']==3))

def _state(db,uid,items,*,now=None,progress_only=False,character=None,quest_ids=None,active_rows=None,actor_identity=None):
    from els_server.domain.guild_quests import weekly as guild_weekly
    from els_server.domain.guild_rules import week as guild_week
    now=int(time.time())if now is None else now
    active=[];level=None;career=None;seals=None;partial=False
    def inventory():
        nonlocal items
        if items is None:items=load_items(db,uid)
        return items
    def character_view(*,complete=False):
        nonlocal character,partial
        if character is None and complete:character=load_character(db,uid)
        if character is None:
            # Career/seal counters consume identity, Artifact validation and
            # owned seals. Native full-unit/reward projections stay in their
            # original loader; profession/adaptation objectives request it.
            character=dict(actor_identity)if actor_identity is not None else load_character(db,uid,identity_only=True)
            a=db.execute('SELECT template,evolution,level,experience,potentials FROM character_artifacts WHERE uid=?',(uid,)).fetchone()
            character['artifact']=dict(template=a[0],evolution=a[1],level=a[2],experience=a[3],potentials=json.loads(a[4]))if a else None
            from els_server.storage.skill_unlocks import saved_groups
            character['skill_seal_groups']=saved_groups(db,uid);partial=True
        if complete and partial:character=load_character(db,uid);partial=False
        return character
    for q,at,g,raw in (erp_scope.active_rows(db,uid)if active_rows is None else active_rows):
        from els_server.domain.periodic_activities import visible as periodic_visible
        if not periodic_visible(q,at,now,active=True):continue
        if (guild_weekly(q)or q==54620)and guild_week(at)!=guild_week(now):continue
        if q==31130:
            from els_server.storage.wedding_quests import visible
            if not visible(db,uid,now):continue
        if quest_ids is not None and q not in quest_ids:continue
        hide=sequence(quest_catalog().quest(q).get('HIDE_QUEST_SKILL',{}))
        if hide:
            if seals is None:
                from els_server.domain.skill_unlocks import unsealed_skills
                seals=set(unsealed_skills(character_view()))
            if any(skill in seals for skill in hide):continue
        counts={int(k):v for k,v in json.loads(raw).items()}
        subs=quest_catalog().objectives(q)
        if set(counts)!={sub['m_iID'] for sub in subs}:raise ValueError('Invalid persisted quest objective keys')
        for sub in subs:
            if sub['m_eClearType']==80:
                from els_server.domain.tutorial_memory8_finale import receipt_progress
                counts[sub['m_iID']]=receipt_progress(sub,completed_ids(db,uid))
        if set(counts)!={s['m_iID'] for s in subs} or any(type(n) is not int or not 0<=n<=target(s) for s in subs for n in [counts[s['m_iID']]]):raise ValueError('Invalid persisted quest objectives')
        for s in subs:
            if s['m_eClearType']==3:counts[s['m_iID']]=min(target(s),_inventory_count(inventory(),s['m_ClearCondition']['m_iCollectionItemID'],quest=q))
            elif s['m_eClearType']==46:counts[s['m_iID']]=1
            elif s['m_eClearType']==31:
                # Same-owner, same-transaction state; saved/client counters
                # cannot satisfy a level objective. No level/EXP mutation.
                if level is None:level=db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()[0]
                counts[s['m_iID']]=int(level>=s['m_ClearCondition']['m_iCharLevel'])
            elif s['m_eClearType']==70:
                # The native objective sums the selected character's active
                # page, including points invested before accepting the task.
                points=0
                if erp_scope.exists(db,'resonance2026_characters'):
                    from els_server.domain.resonance_allocation_flow import profiles
                    pages=profiles(db).pages.read(erp_scope.account(db,uid),uid)
                    if pages is not None and pages.enabled:
                        points=sum(count for _,count in pages.selected().points)
                counts[s['m_iID']]=min(target(s),points)
            if s['m_eClearType']==38:
                from els_server.domain.guild_task35630 import joined
                counts[s['m_iID']]=joined(db,uid,q,s)
            if s['m_eClearType']==81:
                from els_server.domain.growth_guide import objective as guide_objective
                if guide_objective(s):
                    from els_server.storage.growth_guide import saved_progress
                    if career is None:career=character_view()
                    counts[s['m_iID']]=saved_progress(db,uid,s,career)
                    continue
                from els_server.domain.tutorial_progression import career_progress
                if career is None:career=character_view()
                if s['m_iID']==52702:
                    from els_server.domain.el_search_collection import career_progress as collection_career_progress
                    counts[s['m_iID']]=collection_career_progress(s,career)
                else:counts[s['m_iID']]=career_progress(s,career)
            if s['m_eClearType']==121:
                from els_server.domain.el_search_collection import ep_target
                from els_server.storage.ep_points import balance as current_ep
                counts[s['m_iID']]=min(ep_target(s),current_ep(db,uid))
            if s['m_eClearType']==110:
                a=db.execute('SELECT evolution FROM character_artifacts WHERE uid=?',(uid,)).fetchone()
                counts[s['m_iID']]=min(target(s),a[0] if a else 0)
            if s['m_eClearType'] in (82,107,109,117):
                from els_server.domain.growth_guide import objective as guide_objective
                if guide_objective(s):
                    from els_server.storage.growth_guide import saved_progress
                    career=character_view(complete=s['m_eClearType']in(82,109))
                    counts[s['m_iID']]=saved_progress(db,uid,s,career,items=inventory())
        from els_server.domain.periodic_activities import contains as periodic_contains
        active.append(dict(id=q,owner=erp_scope.quest_owner(db,uid,q),accepted_at=at,generation=g,objectives=counts,**({'projection_owner':uid} if q in (25600,25601,25602,25610,25611,25612,37100,45000,54620) or periodic_contains(q) else {})))
    if progress_only:return dict(active=active)
    from els_server.domain.periodic_activities import visible as periodic_visible
    done=[dict(id=q,completed_at=at) for q,at in erp_scope.completed_rows(db,uid)
          if periodic_visible(q,at,now,active=False)and((not guild_weekly(q)and q not in(31130,54620))or guild_week(at)==guild_week(now))]
    state=dict(active=active,completed=done)
    from els_server.storage.weapon_growth import snapshot as weapon_growth_snapshot
    growth=weapon_growth_snapshot(db,uid,inventory())
    if growth['item_active'] or growth['item_completed']:state.update(growth)
    return state

class QuestState:
    def __init__(self,path,uid=1001,*,account_id=None,account_source_guard=None):
        self.path=path;self.uid=character_uid(uid);self.account_id=account_id;self.account_source_guard=account_source_guard

    def snapshot(self):
        from els_server.storage.read_scope import quest_notification_projection
        return quest_notification_projection(self,self._snapshot,projection='quest-state')

    def _snapshot(self):
        # Existing quest snapshots are projections, not mutations. The same
        # read-only consumer is already used by notification_snapshot; only
        # an uninitialized store needs the original schema writer below.
        with snapshot_connection(self.path) as db:
            db.execute('BEGIN')
            tables=('character_ep','character_quests','completed_quests','quest_actions','quest_progress_events')
            if all(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone()for t in tables):
                with _table_snapshot(db):
                    identity=load_character(db,self.uid,self.account_id,identity_only=True)
                    return _state(db,self.uid,load_items(db,self.uid),actor_identity=identity)
        with closing(sqlite3.connect(self.path,timeout=10)) as db:
            with write_transaction(db):
                character=load_character(db,self.uid,self.account_id);ensure(db)
                return _state(db,self.uid,load_items(db,self.uid),character=character)

    def notification_snapshot(self):
        from els_server.storage.read_scope import quest_notification_projection
        return quest_notification_projection(self,self._notification_snapshot)

    def _notification_snapshot(self):
        # Existing task state only: no initialization, completion or rewards.
        with snapshot_connection(self.path) as db:
            db.execute('BEGIN')
            with _table_snapshot(db):
                identity=load_character(db,self.uid,self.account_id,identity_only=True)
                if not all(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(t,)).fetchone() for t in ('character_quests','completed_quests')):return dict(active=[],completed=[])
                return _state(db,self.uid,load_items(db,self.uid),actor_identity=identity)

    def completed(self):
        with snapshot_connection(self.path) as db:
            load_character(db,self.uid,self.account_id,identity_only=True);return completed_ids(db,self.uid)

    def passive_objective_kinds(self):
        """Read active observation needs without a writer lock or schema edits."""
        with snapshot_connection(self.path) as db:
            db.execute('BEGIN')
            with _table_snapshot(db):
                load_character(db,self.uid,self.account_id,identity_only=True)
                if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_quests'").fetchone():return frozenset()
                return frozenset(s['m_eClearType'] for qid,at,g,raw in erp_scope.active_rows(db,self.uid)
                                 for s in quest_catalog().objectives(qid))

    def collection_snapshot(self,*,include_growth=False):
        """Read one consistent view without creating tables or taking a writer lock."""
        with snapshot_connection(self.path) as db:
            db.execute('BEGIN')
            with _table_snapshot(db):
                character=load_character(db,self.uid,self.account_id,identity_only=not include_growth)
                present=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_quests'").fetchone()
                active=erp_scope.active_rows(db,self.uid,quest_ids=None if include_growth else collection_quest_ids())if present else ()
                identities={qid for qid,at,g,raw in active
                            if any(s['m_eClearType'] in SAVED_OBJECTIVE_KINDS for s in quest_catalog().objectives(qid))}
                if not include_growth:
                    if not identities:return []
                    return _state(db,self.uid,None,progress_only=True,quest_ids=identities,active_rows=active,actor_identity=character)['active']
                items=load_items(db,self.uid)
                if present:
                    state=_state(db,self.uid,items,character=character,active_rows=active)
                else:
                    from els_server.storage.weapon_growth import snapshot as growth_snapshot
                    state=dict(active=[],completed=[],**growth_snapshot(db,self.uid,items))
                rows=[row for row in state['active'] if row['id'] in identities]
                if not include_growth:return rows
                state.setdefault('item_active',[]);state.setdefault('item_completed',[])
                return rows,state

    def action(self,kind,request,operation_id,encode,*,now=None,location=None,transaction=None):
        if kind not in ('accept','abandon','claim'):raise ValueError('Quest action')
        if not isinstance(operation_id,str) or not 1<=len(operation_id)<=200:raise ValueError('Quest operation identity')
        now=int(time.time()) if now is None else now
        if type(now) is not int or not 0<now<2**63:raise ValueError('Quest timestamp')
        digest=hashlib.sha256(json.dumps([self.uid,kind,request],sort_keys=True).encode()).hexdigest()
        uid=self.uid;qid=request['quest'];q=quest_catalog().quest(qid)
        from els_server.domain.photo_zone_catalog import quests as photo_quests
        photo_scoped=str(qid)in photo_quests()
        def photo_guard(db):
            if not callable(self.account_source_guard):raise ValueError('Studio quest requires current actor guard')
            self.account_source_guard(db)
        if qid in range(169600,169605) and kind=='abandon':raise ValueError('Quick Start automatic task cannot be abandoned')
        if qid==22164 and kind=='accept':raise ValueError('Retired22164 retains saved readers only')
        from els_server.domain.epic_skip import requested as skip_requested,reward as skip_reward
        skipping=kind=='claim' and skip_requested(request)
        def skip_guard(db):
            if not callable(self.account_source_guard) or type(self.account_id) is not int or self.account_id<=0:
                raise ValueError('Epic skip requires current actor/session guard')
            self.account_source_guard(db)
        with _progress_connection(self.path,transaction) as db:
            if photo_scoped:photo_guard(db)
            character=load_character(db,uid,self.account_id)
            if qid in range(169600,169605):
                if not callable(self.account_source_guard):raise ValueError('Quick Start current actor guard required')
                self.account_source_guard(db)
            if qid==35630:
                from els_server.domain.guild_task35630 import action_guard as guild_action_guard
                guild_action_guard(self,db,kind,request)
            if skipping:skip_guard(db)
            ensure(db)
            from els_server.storage.periodic_quest_scope import prepare as periodic_prepare
            periodic_prepare(self,db,qid,operation_id,kind,now)
            if qid==54620:
                from els_server.storage import pet_battle_quest_scope as pet_weekly_tasks
                pet_weekly_tasks.prepare(self,db,operation_id,kind,now)
            if qid==31130:
                from els_server.storage import wedding_quests as wedding_tasks
                wedding_tasks.before_action(self,db,operation_id,kind,now)
            from els_server.domain.mentor_quests import contains as mentor_contains
            if mentor_contains(qid):
                from els_server.storage import mentor_quests as mentor_tasks
                mentor_tasks.before_action(self,db,qid,operation_id,kind,now)
            from els_server.domain.guild_quests import contains as guild_contains
            if guild_contains(qid):
                from els_server.storage.guild_quests import before_action as guild_before_action,after_action as guild_after_action
                guild_before_action(self,db,qid,operation_id,kind,now)
            if qid==26770:
                from els_server.domain.housing_room_quest import before_action as housing_before_action
                housing_before_action(db,uid,self.account_id,kind,self.account_source_guard)
            if qid==52700:
                from els_server.storage.el_search_collection import before_action as collection_before_action
                collection_before_action(db,uid,self.account_id,kind,self.account_source_guard)
            if erp_scope.scoped(qid):erp_scope.before_action(db,uid,self.account_id,kind,self.account_source_guard,qid=qid)
            if location is None:location=('town',db.execute('SELECT town FROM location WHERE uid=?',(uid,)).fetchone()[0])
            old=db.execute('SELECT owner,kind,request_hash FROM quest_actions WHERE operation_id=?',(operation_id,)).fetchone()
            if old and old!=(uid,kind,digest):raise ValueError('Conflicting quest retry')
            items=load_items(db,uid)
            before=_state(db,uid,items,now=now);active=next((r for r in before['active'] if r['id']==qid),None)
            done=next((r for r in before['completed'] if r['id']==qid),None);replayed=bool(old)
            awards=[];consumed=[]
            stage_changed=False;class_changed=False;accepted_after=()
            if not old:
                if kind=='accept':
                    if done:raise ValueError('Quest already rewarded')
                    require_eligible(character,q,completed_ids(db,uid),items,location=location)
                    if request.get('npc') not in (q['m_eStartNPCID'],10025) and q['m_eStartNPCID']!=0:raise ValueError('Quest start NPC mismatch')
                    from els_server.domain.job_quests import catalog as job_catalog
                    if str(qid) in job_catalog()['quests'] and any(
                        row['id']!=qid and quest_catalog().quest(row['id'])['m_eQuestType'] in (2,9) for row in before['active']):
                        raise ValueError('Another class advancement quest is active')
                    if active:replayed=True
                    else:
                        if not acceptance_available(q,before['active']):raise ValueError('Side quest capacity')
                        counts={s['m_iID']:0 for s in quest_catalog().objectives(qid)}
                        for s in quest_catalog().objectives(qid):
                            if s['m_eClearType']==24 and location[0]=='town' and location[1] in sequence(s['m_ClearCondition']['m_eVillageID']):counts[s['m_iID']]=1
                        # Admitted town dialogue receipts bind a unique accepted action,
                        # including abandon/reaccept within one wall-clock second.
                        from els_server.domain.town_dialogue import catalog as town_catalog
                        from els_server.domain.mainline_find_npc import catalog as find_catalog
                        generation=now if qid!=26770 and qid!=35630 and qid not in (25600,25601,25602,25610,25611,25612,45000,31130,54620) and str(qid) not in town_catalog()['quests'] and qid not in find_catalog()['quest_ids']and not guild_contains(qid)and not mentor_contains(qid)else db.execute('SELECT COALESCE(MAX(rowid),0)+1 FROM quest_actions').fetchone()[0]
                        erp_scope.insert_active(db,uid,qid,now,generation,json.dumps(counts,sort_keys=True))
                elif kind=='abandon':
                    if done:raise ValueError('Completed quest cannot be abandoned')
                    erp_scope.delete_active(db,uid,qid)
                elif done:replayed=True
                else:
                    # 3046B60 ->7CFF80 forwards skip in the SECOND F4 flag.
                    # The first native flag remains an unsupported mode.
                    if request.get('flags',(0,))[0]:raise ValueError('Unsupported quest completion mode')
                    if active is None:raise ValueError('Quest has not been accepted')
                    require_eligible(character,q,completed_ids(db,uid),items,location=location,check_location=request.get('npc')!=0)
                    # 3030D10 forwards the quest window's NPC context as-is;
                    # remote/quick completion uses zero (no NPC conversation).
                    if request.get('npc') not in (0,q['m_eEndNPCID'],10025):raise ValueError('Quest end NPC mismatch')
                    subs=quest_catalog().objectives(qid)
                    reward=skip_reward(character,q,quest_catalog()) if skipping else q['Reward']
                    if not skipping and any(active['objectives'][s['m_iID']]<target(s) for s in subs):raise QuestIncomplete('Quest objectives are incomplete')
                    from els_server.domain.quest_selection import selected_rewards
                    selection=selected_rewards(q,request.get('choices',()),character=character)
                    # Real collection items are consumed in the same transaction;
                    # quest-only drops live in the task counters, never the bag.
                    needs={}
                    for s in (() if skipping else subs):
                        if s['m_eClearType']==3:
                            template=s['m_ClearCondition']['m_iCollectionItemID'];needs[template]=needs.get(template,0)+target(s)
                    for template,n in needs.items():
                        if _inventory_count(items,template,quest=qid)<n:raise QuestIncomplete('Quest collection changed')
                        # Approved local45000 rule: possession is checked on
                        # this recipient's current bag, without a material debit.
                        if qid==45000:continue
                        from els_server.domain.item_locks import locked
                        from els_server.domain.item_expiration import expired
                        for item in items:
                            if item['template']!=template or item['group']==9 or locked(item) or expired(item) or qid==25600 and item['group']!=3:continue
                            from els_server.domain.cartridge_registration_rules import require_unbound
                            require_unbound(db,item['uid'])
                            take=min(n,item['count']);n-=take
                            if take==item['count']:
                                from els_server.storage.item_expiration import forget
                                from els_server.storage.item_locks import forget as forget_lock
                                forget(db,item['uid']);forget_lock(db,item['uid']);db.execute('DELETE FROM inventory_items WHERE owner=? AND uid=?',(uid,item['uid']))
                                consumed.append(((item['group'],item['slot']),None))
                            else:
                                db.execute('UPDATE inventory_items SET count=count-? WHERE owner=? AND uid=?',(take,uid,item['uid']));consumed.append(((item['group'],item['slot']),dict(item,count=item['count']-take)))
                            if not n:break
                    if qid==52700:
                        from els_server.storage.el_search_collection import activate as activate_collection
                        activate_collection(db,uid,self.account_id,character,now)
                    if any(reward.get(k,0) for k in ('m_iSP','m_iBuff')):raise ValueError('Unsupported native quest reward')
                    ep=reward.get('m_iEP',0)
                    from els_server.storage.ep_points import credit as credit_ep
                    credit_ep(db,uid,ep)
                    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
                    plan=[]
                    from els_server.domain.periodic_activities import ordinary_weekly
                    for r in (()if mentor_contains(qid)or qid in(31130,54620)or ordinary_weekly(qid) else sequence(reward.get('m_vecItem',{}))+selection):
                        t=r['m_iItemID']
                        if r['m_sSocketOption'] or t not in VERIFIED_TEMPLATES:raise ValueError('Unverified native quest reward item')
                        if r['m_iPeriod']:
                            if guild_contains(qid):
                                from els_server.domain.guild_quests import timed_plan
                                plan.append(timed_plan(q,r,now))
                            elif qid==39480:
                                from els_server.domain.reselection_quest import timed_plan
                                plan.append(timed_plan(q,r,now=now))
                            elif qid in (32030,35490):
                                from els_server.domain.special_quest_rewards import timed_plan
                                plan.append(timed_plan(q,r,now=now))
                            else:
                                from els_server.domain.travel_pass import quest_reward_plan
                                plan.append(quest_reward_plan(q,r,now=int(time.time())))
                        else:plan.append(dict(template=t,metadata=VERIFIED_TEMPLATES[t],quantity=r['m_iQuantity'],group=TEMPLATE_BAG_GROUPS[t]))
                    from els_server.domain.growth_guide import contains as guide_contains
                    if mentor_contains(qid):awards=mentor_tasks.grant(self,db,qid,operation_id,now)
                    elif qid==31130:awards=wedding_tasks.grant(self,db,operation_id,now)
                    elif qid==54620:awards=pet_weekly_tasks.grant(self,db,operation_id,now)
                    elif ordinary_weekly(qid):awards=erp_scope.grant_weekly(self,db,qid,operation_id,now)
                    else:awards=grant_items(db,plan,uid,growth_guide_quest=qid if guide_contains(qid)else None)if plan else []
                    ed,xp=reward['m_iED'],reward['m_iEXP']
                    if any(type(v) is not int or v<0 for v in (ed,xp)):raise ValueError('Quest reward balance')
                    # Ordinary EXP uses the same current-client level ceiling
                    # as normal combat. Never reduce an existing saved balance,
                    # or reinterpret ordinary quest EXP as an ERP source.
                    from els_server.game_data import client_data
                    ordinary_limit=min(2**31-1,client_data().thresholds[-1])
                    saved_experience=db.execute('SELECT experience FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
                    if type(saved_experience) is not int or not 0<=saved_experience<2**63:raise ValueError('Quest saved experience')
                    xp=min(xp,max(0,ordinary_limit-saved_experience))
                    db.execute('UPDATE reward_balances SET ed=ed+?,experience=experience+?,revision=revision+1 WHERE uid=?',(ed,xp,uid))
                    if xp:
                        from els_server.game_data import client_data
                        experience=db.execute('SELECT experience FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
                        level=client_data().level_for_experience(experience)
                        old_level=db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()[0]
                        changed=db.execute('UPDATE characters SET level=?,revision=revision+1 WHERE uid=? AND level<?',(level,uid,level)).rowcount
                        if changed:
                            from els_server.storage.normal_fatigue import level_up as normal_fatigue_level_up
                            normal_fatigue_level_up(db,self.path,uid,self.account_id,'quest:'+operation_id,digest,old_level,level)
                    if reward.get('m_eChangeUnitClass',0):
                        from els_server.storage.careers import apply_quest_transition
                        old_career,new_career=apply_quest_transition(db,uid,q)
                        class_changed=old_career['unit_class']!=new_career['unit_class']
                        stage_changed=(old_career['transcendence'],old_career['master'])!=(new_career['transcendence'],new_career['master'])
                    from els_server.storage.artifact_progression import complete_quest as complete_artifact_quest
                    complete_artifact_quest(db,uid,qid)
                    erp_scope.delete_active(db,uid,qid)
                    saved_reward=dict(ed=ed,experience=xp,items=awards,consumed_positions=[pos for pos,_ in consumed])
                    if skipping:saved_reward['skipped']=True
                    if selection:saved_reward['selected_templates']=[r['m_iItemID'] for r in selection]
                    if ep:saved_reward['ep']=ep
                    erp_scope.insert_completed(db,uid,qid,now,saved_reward)
                    from els_server.storage.season_pass import advance as pass_advance
                    pass_advance(self,db,'quest',qid,now)
                    if guild_contains(qid)and reward.get('m_iGuildHonorPoint',0):
                        from els_server.storage.guild_quests import honor as guild_honor
                        guild_honor(db,uid,reward['m_iGuildHonorPoint'],operation_id,0xf4,digest,now)
                    from els_server.storage.epic_followups import accept_after_reward
                    accepted_after=() if erp_scope.scoped(qid) else accept_after_reward(db,uid,qid,load_character(db,uid,self.account_id),load_items(db,uid),location,now)
                if kind=='claim' and qid in range(169600,169605):
                    from els_server.storage.quick_start import accept_next
                    accepted_after+=accept_next(db,uid,now)
                db.execute('INSERT INTO quest_actions VALUES (?,?,?,?)',(operation_id,uid,kind,digest))
            if qid==31130:wedding_tasks.after_action(self,db,operation_id,kind,now)
            # Accept/abandon only change quest rows in this writer. Reuse the
            # already fully validated bag; a saved SQL trigger may change it,
            # and rewards/claims retain their original complete reload.
            if kind=='claim' or db.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' UNION ALL SELECT 1 FROM sqlite_temp_master WHERE type='trigger' LIMIT 1").fetchone():items=load_items(db,uid)
            character=load_character(db,uid,self.account_id);state=_state(db,uid,items,now=now,character=character)
            career_refresh=class_changed
            if kind=='claim' and replayed:
                saved=erp_scope.reward_row(db,uid,qid)
                if saved:
                    saved=json.loads(saved[0]);ids={i['uid'] for i in saved['items']}
                    awards=[i for i in items if i['uid'] in ids]
                    consumed=[(tuple(pos),next((i for i in items if (i['group'],i['slot'])==tuple(pos)),None)) for pos in saved.get('consumed_positions',[])]
                    career_refresh=bool(q['Reward'].get('m_eChangeUnitClass',0))
            from els_server.storage.reward_state import validate_balances
            balances=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(uid,)).fetchone())
            result=dict(replayed=replayed,state=state,character=character,balances=balances,items=items,updates=awards,consumed=consumed,slots=current_slots(db,character))
            from els_server.domain.periodic_activities import pass_task
            if pass_task(qid):
                from els_server.storage.season_pass import state as pass_state
                result['pass_status']=pass_state(db,self.account_id,q['m_eSeasonPassCategory'],now)
            result['accepted_after']=[row for row in state['active'] if row['id'] in accepted_after]
            if stage_changed:result['stage_changed']=True
            if class_changed:result['class_changed']=True
            if career_refresh:result['career_refresh']=True
            # All responses, including full unit and inventory bodies, must be
            # encodable before SQL commit. No stale receipt inventory deltas.
            if erp_scope.scoped(qid):erp_scope.before_action(db,uid,self.account_id,kind,self.account_source_guard,qid=qid)
            if skipping:skip_guard(db)
            if qid==35630:guild_action_guard(self,db,kind,request)
            if qid==52700:collection_before_action(db,uid,self.account_id,kind,self.account_source_guard)
            if qid==26770:housing_before_action(db,uid,self.account_id,kind,self.account_source_guard)
            if guild_contains(qid):guild_after_action(self,db,qid,operation_id,kind,now)
            if mentor_contains(qid):mentor_tasks.after_action(self,db,qid,operation_id,kind,now)
            result['events']=encode(result)
            from els_server.domain.periodic_activities import contains as periodic_contains
            if qid in(31130,54620)or periodic_contains(qid):
                from els_server.protocol.protocol_codec import encode_event
                for event in result['events']:encode_event(event)
                self.account_source_guard(db)
            if mentor_contains(qid):
                from els_server.protocol.protocol_codec import encode_event
                for event in result['events']:encode_event(event)
                mentor_tasks.actor(self,db,qid,kind)
            if guild_contains(qid):
                from els_server.protocol.protocol_codec import encode_event
                for event in result['events']:encode_event(event)
                self.account_source_guard(db)
            if photo_scoped:photo_guard(db)
            if qid in range(169600,169605):self.account_source_guard(db)
            if qid==26770:housing_before_action(db,uid,self.account_id,kind,self.account_source_guard)
            if qid==35630:
                from els_server.protocol.protocol_codec import encode_event
                for event in result['events']:encode_event(event)
                guild_action_guard(self,db,kind,request)
            if qid==52700:collection_before_action(db,uid,self.account_id,kind,self.account_source_guard)
            if skipping:skip_guard(db)
            if erp_scope.scoped(qid):erp_scope.before_action(db,uid,self.account_id,kind,self.account_source_guard,qid=qid)
            if not isinstance(result['events'],list) or any(not isinstance(e.payload,bytes) or len(e.payload)>65536 for e in result['events']):raise ValueError('Quest response bound')
            return result

    def record(self,event_id,event,proof,*,validate=None,prepare=None,transaction=None):
        if not isinstance(event_id,str) or not 1<=len(event_id)<=200 or not isinstance(proof,bytes) or not proof:raise ValueError('Quest progress evidence')
        if event.get('kind') not in ('kill','clear','stage_clear','visit_town','visit_dungeon') or type(event.get('dungeon')) is not int or type(event.get('level')) is not int:raise ValueError('Quest progress event')
        if event['kind']=='kill' and type(event.get('npc')) is not int:raise ValueError('Quest NPC event')
        if event['kind']=='visit_town' and type(event.get('town')) is not int:raise ValueError('Quest town event')
        digest=hashlib.sha256(proof).hexdigest();raw=json.dumps(event,sort_keys=True)
        roll_proof=progress_proof(self.uid,event_id,proof)
        if transaction is not None and (type(self.account_id) is not int or self.account_id<=0):
            raise ValueError('Quest shared progress requires an account owner')
        with _progress_connection(self.path,transaction) as db:
            identity=load_character(db,self.uid,self.account_id,identity_only=True);ensure(db)
            old=db.execute('SELECT proof_hash,event_json FROM quest_progress_events WHERE owner=? AND event_id=?',(self.uid,event_id)).fetchone()
            if validate is not None:validate(db)
            if old:
                if old!=(digest,raw):raise ValueError('Conflicting quest progress retry')
                return prepare([],True) if prepare is not None else []
            from els_server.domain.guild_quests import contains as guild_contains
            from els_server.storage.guild_quests import rollover as guild_rollover
            from els_server.storage.guild_membership_state import snapshot as guild_snapshot
            guild_member=guild_snapshot(db,self.uid,self.account_id)is not None if self.account_id is not None else False
            now=int(time.time())
            if guild_member:guild_rollover(db,self.uid,now)
            # Progress only consumes active objectives. Inventory and extended
            # character state are read lazily if those objectives require them;
            # completed/item-task projections belong to snapshot/reward paths.
            quest_ids=None;active_rows=erp_scope.active_rows(db,self.uid)
            from els_server.domain.periodic_activities import contains as periodic_contains,pass_task,visible as periodic_visible
            if any(pass_task(q)and not periodic_visible(q,at,now,active=True)for q,at,_,_ in active_rows):
                from els_server.storage.season_pass import restore as restore_pass
                restore_pass(self,db,now);active_rows=erp_scope.active_rows(db,self.uid)
            if event['kind']=='kill' and 'tutorial_quest'not in event:
                # The existing increment consumer returns zero for all other
                # ordinary objective kinds on kills. A mixed task keeps every
                # subobjective; scoped source consumers are always retained.
                quest_ids={q for q,at,g,raw in active_rows
                    if erp_scope.scoped(q)and not periodic_contains(q)or any(s['m_eClearType']in(2,4,27,71)for s in quest_catalog().objectives(q))}
            state=_state(db,self.uid,None,now=now,progress_only=True,quest_ids=quest_ids,active_rows=active_rows,actor_identity=identity);changed=[]
            for row in state['active']:
                from els_server.domain.mentor_quests import contains as mentor_contains
                if mentor_contains(row['id'])or row['id']==31130:continue
                if guild_contains(row['id'])and not guild_member:continue
                if erp_scope.scoped(row['id']) and not erp_scope.progress_allowed(db,self.uid,self.account_id,event_id,event,proof,self.account_source_guard,qid=row['id']):continue
                counts=dict(row['objectives'])
                for s in quest_catalog().objectives(row['id']):
                    from els_server.domain.mainline_subquest_groups import can_progress
                    if not can_progress(quest_catalog().quest(row['id']),s,row['objectives']):continue
                    i=s['m_iID'];delta=objective_increment(s,event,roll_proof)
                    from els_server.domain.growth_guide import objective as guide_objective
                    counts[i]=max(counts[i],delta) if s['m_eClearType']==71 and guide_objective(s) else min(target(s),counts[i]+delta)
                if counts!=row['objectives']:
                    erp_scope.update_objectives(db,self.uid,row['id'],counts)
                    changed.append(dict(row,objectives=counts))
            from els_server.protocol.quest_messages import progress
            events=[progress(changed)] if changed else []
            if(event['kind'],event['dungeon'],event.get('npc'))==('kill',38300,1367):
                producer=getattr(self.account_source_guard,'mentor_black_gate',None)
                if producer is not None:events+=producer(db,event_id,event,proof)
            if any(guild_contains(row['id'])for row in changed):
                from els_server.protocol.protocol_codec import encode_event
                for response in events:encode_event(response)
                if not callable(self.account_source_guard):raise ValueError('Guild quest producer requires current actor')
                self.account_source_guard(db)
            if any(row['id']==45000 for row in changed):
                from els_server.protocol.protocol_codec import encode_event
                for response in events:encode_event(response)
                erp_scope.before_action(db,self.uid,self.account_id,'progress',self.account_source_guard,qid=45000)
            if any(periodic_contains(row['id'])for row in changed):
                from els_server.protocol.protocol_codec import encode_event
                for response in events:encode_event(response)
                erp_scope._guard(db,self.uid,self.account_id,self.account_source_guard)
            # Passive observations may run before a rejected request. Do not
            # create audit receipts for idle/no-task town or discovery polls.
            if not changed and event['kind'] in ('visit_town','visit_dungeon'):return []
            db.execute('INSERT INTO quest_progress_events VALUES (?,?,?,?)',(self.uid,event_id,digest,raw))
            return prepare(events,False) if prepare is not None else events

from els_server.storage.read_scope import snapshot_connection

from els_server.storage.sqlite_timing import write_transaction
