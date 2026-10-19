"""Atomic quest state, progress evidence, inventory consumption and rewards."""
from contextlib import closing
import hashlib,json,sqlite3,struct,time
from els_server.domain.seal_quests import quest_catalog,sequence,require_eligible,target,objective_increment,ACTIVE_QUEST_LIMIT
from els_server.storage.character_schema import character_uid
from els_server.storage.inventory_state import load_items,grant_items


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
    return frozenset(r[0] for r in db.execute('SELECT quest FROM completed_quests WHERE owner=?',(uid,)))

def load_character(db,uid,account_id=None):
    from els_server.storage.characters import Characters
    from els_server.storage.skill_unlocks import saved_groups
    from els_server.storage.skill_expansion import is_expanded
    from els_server.storage.bag_capacity import saved_capacities
    if account_id is not None and db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()!=(account_id,):raise ValueError('Quest character owner mismatch')
    row=Characters._row(db.execute('SELECT uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters WHERE uid=?',(uid,)).fetchone())
    a=db.execute('SELECT template,evolution,level,experience,potentials FROM character_artifacts WHERE uid=?',(uid,)).fetchone()
    row['artifact']=dict(template=a[0],evolution=a[1],level=a[2],experience=a[3],potentials=json.loads(a[4])) if a else None
    from els_server.storage.ep_points import balance as ep_balance
    ep=ep_balance(db,uid)
    if ep:row['ep']=ep
    row['skill_seal_groups']=saved_groups(db,uid);row['skill_row_expanded']=is_expanded(db,uid);row['bag_capacities']=saved_capacities(db,uid)
    return row

def current_slots(db,character):
    from els_server.domain.skill_rules import upgraded_slots
    from els_server.domain.character_rules import default_slots
    row=db.execute('SELECT payload FROM skill_slots WHERE uid=?',(character['uid'],)).fetchone()
    return upgraded_slots(struct.unpack('>22i',row[0]),character) if row else default_slots(character)

def _inventory_count(items,template):
    from els_server.domain.item_expiration import expired
    from els_server.domain.item_locks import locked
    return sum(i['count'] for i in items if i['template']==template and i['group']!=9 and not expired(i) and not locked(i))

def _state(db,uid,items):
    active=[];level=None;career=None
    for q,at,g,raw in db.execute('SELECT quest,accepted_at,generation,objectives FROM character_quests WHERE owner=? ORDER BY quest',(uid,)):
        counts={int(k):v for k,v in json.loads(raw).items()}
        subs=quest_catalog().objectives(q)
        if set(counts)!={sub['m_iID'] for sub in subs}:raise ValueError('Invalid persisted quest objective keys')
        for sub in subs:
            if sub['m_eClearType']==80:
                from els_server.domain.tutorial_memory8_finale import receipt_progress
                counts[sub['m_iID']]=receipt_progress(sub,completed_ids(db,uid))
        if set(counts)!={s['m_iID'] for s in subs} or any(type(n) is not int or not 0<=n<=target(s) for s in subs for n in [counts[s['m_iID']]]):raise ValueError('Invalid persisted quest objectives')
        for s in subs:
            if s['m_eClearType']==3:counts[s['m_iID']]=min(target(s),_inventory_count(items,s['m_ClearCondition']['m_iCollectionItemID']))
            elif s['m_eClearType']==46:counts[s['m_iID']]=1
            elif s['m_eClearType']==31:
                # Same-owner, same-transaction state; saved/client counters
                # cannot satisfy a level objective. No level/EXP mutation.
                if level is None:level=db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()[0]
                counts[s['m_iID']]=int(level>=s['m_ClearCondition']['m_iCharLevel'])
            if s['m_eClearType']==81:
                from els_server.domain.tutorial_progression import career_progress
                if career is None:career=load_character(db,uid)
                counts[s['m_iID']]=career_progress(s,career)
            if s['m_eClearType']==110:
                a=db.execute('SELECT evolution FROM character_artifacts WHERE uid=?',(uid,)).fetchone()
                counts[s['m_iID']]=min(target(s),a[0] if a else 0)
        active.append(dict(id=q,owner=uid,accepted_at=at,generation=g,objectives=counts))
    done=[dict(id=q,completed_at=at) for q,at in db.execute('SELECT quest,completed_at FROM completed_quests WHERE owner=? ORDER BY quest',(uid,))]
    return dict(active=active,completed=done)

class QuestState:
    def __init__(self,path,uid=1001,*,account_id=None):
        self.path=path;self.uid=character_uid(uid);self.account_id=account_id

    def snapshot(self):
        with closing(sqlite3.connect(self.path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE');load_character(db,self.uid,self.account_id);ensure(db)
            return _state(db,self.uid,load_items(db,self.uid))

    def completed(self):
        with closing(sqlite3.connect(self.path,timeout=10)) as db:
            load_character(db,self.uid,self.account_id);return completed_ids(db,self.uid)

    def passive_objective_kinds(self):
        """Read active observation needs without a writer lock or schema edits."""
        with closing(sqlite3.connect(self.path,timeout=10)) as db,db:
            db.execute('BEGIN');load_character(db,self.uid,self.account_id)
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_quests'").fetchone():return frozenset()
            return frozenset(s['m_eClearType'] for qid, in db.execute('SELECT quest FROM character_quests WHERE owner=?',(self.uid,))
                             for s in quest_catalog().objectives(qid))

    def collection_snapshot(self):
        """Read one consistent view without creating tables or taking a writer lock."""
        with closing(sqlite3.connect(self.path,timeout=10)) as db,db:
            db.execute('BEGIN');load_character(db,self.uid,self.account_id)
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_quests'").fetchone():return []
            identities={qid for qid, in db.execute('SELECT quest FROM character_quests WHERE owner=?',(self.uid,))
                        if any(s['m_eClearType'] in (3,31,80,81,110) for s in quest_catalog().objectives(qid))}
            if not identities:return []
            return [row for row in _state(db,self.uid,load_items(db,self.uid))['active'] if row['id'] in identities]

    def action(self,kind,request,operation_id,encode,*,now=None,location=None):
        if kind not in ('accept','abandon','claim'):raise ValueError('Quest action')
        if not isinstance(operation_id,str) or not 1<=len(operation_id)<=200:raise ValueError('Quest operation identity')
        now=int(time.time()) if now is None else now
        if type(now) is not int or not 0<now<2**63:raise ValueError('Quest timestamp')
        digest=hashlib.sha256(json.dumps([self.uid,kind,request],sort_keys=True).encode()).hexdigest()
        uid=self.uid;qid=request['quest'];q=quest_catalog().quest(qid)
        with closing(sqlite3.connect(self.path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE');character=load_character(db,uid,self.account_id);ensure(db)
            if location is None:location=('town',db.execute('SELECT town FROM location WHERE uid=?',(uid,)).fetchone()[0])
            old=db.execute('SELECT owner,kind,request_hash FROM quest_actions WHERE operation_id=?',(operation_id,)).fetchone()
            if old and old!=(uid,kind,digest):raise ValueError('Conflicting quest retry')
            items=load_items(db,uid);before=_state(db,uid,items);active=next((r for r in before['active'] if r['id']==qid),None)
            done=next((r for r in before['completed'] if r['id']==qid),None);replayed=bool(old)
            awards=[];consumed=[]
            if not old:
                if kind=='accept':
                    if done:raise ValueError('Quest already rewarded')
                    require_eligible(character,q,completed_ids(db,uid),items,location=location)
                    if request.get('npc') not in (q['m_eStartNPCID'],10025) and q['m_eStartNPCID']!=0:raise ValueError('Quest start NPC mismatch')
                    if active:replayed=True
                    else:
                        if len(before['active'])>=ACTIVE_QUEST_LIMIT:raise ValueError('Local active quest capacity')
                        counts={s['m_iID']:0 for s in quest_catalog().objectives(qid)}
                        for s in quest_catalog().objectives(qid):
                            if s['m_eClearType']==24 and location[0]=='town' and location[1] in sequence(s['m_ClearCondition']['m_eVillageID']):counts[s['m_iID']]=1
                        # Admitted town dialogue receipts bind a unique accepted action,
                        # including abandon/reaccept within one wall-clock second.
                        from els_server.domain.town_dialogue import catalog as town_catalog
                        generation=now if str(qid) not in town_catalog()['quests'] else db.execute('SELECT COALESCE(MAX(rowid),0)+1 FROM quest_actions').fetchone()[0]
                        db.execute('INSERT INTO character_quests VALUES (?,?,?,?,?)',(uid,qid,now,generation,json.dumps(counts,sort_keys=True)))
                elif kind=='abandon':
                    if done:raise ValueError('Completed quest cannot be abandoned')
                    db.execute('DELETE FROM character_quests WHERE owner=? AND quest=?',(uid,qid))
                elif done:replayed=True
                else:
                    # The original first F4 flag denotes skipped Epic rewards
                    # (half ED / no EXP or EP). Skipping is not implemented;
                    # never reinterpret that request as a full-reward claim.
                    if request.get('flags',(0,))[0]:raise ValueError('Quest skipping is unsupported')
                    if active is None:raise ValueError('Quest has not been accepted')
                    require_eligible(character,q,completed_ids(db,uid),items,location=location)
                    # 3030D10 forwards the quest window's NPC context as-is;
                    # remote/quick completion uses zero (no NPC conversation).
                    if request.get('npc') not in (0,q['m_eEndNPCID'],10025):raise ValueError('Quest end NPC mismatch')
                    subs=quest_catalog().objectives(qid)
                    if any(active['objectives'][s['m_iID']]<target(s) for s in subs):raise QuestIncomplete('Quest objectives are incomplete')
                    from els_server.domain.quest_selection import selected_rewards
                    selection=selected_rewards(q,request.get('choices',()),character=character)
                    # Real collection items are consumed in the same transaction;
                    # quest-only drops live in the task counters, never the bag.
                    needs={}
                    for s in subs:
                        if s['m_eClearType']==3:
                            template=s['m_ClearCondition']['m_iCollectionItemID'];needs[template]=needs.get(template,0)+target(s)
                    for template,n in needs.items():
                        if _inventory_count(items,template)<n:raise QuestIncomplete('Quest collection changed')
                        from els_server.domain.item_locks import locked
                        from els_server.domain.item_expiration import expired
                        for item in items:
                            if item['template']!=template or item['group']==9 or locked(item) or expired(item):continue
                            take=min(n,item['count']);n-=take
                            if take==item['count']:
                                from els_server.storage.item_expiration import forget
                                from els_server.storage.item_locks import forget as forget_lock
                                forget(db,item['uid']);forget_lock(db,item['uid']);db.execute('DELETE FROM inventory_items WHERE owner=? AND uid=?',(uid,item['uid']))
                                consumed.append(((item['group'],item['slot']),None))
                            else:
                                db.execute('UPDATE inventory_items SET count=count-? WHERE owner=? AND uid=?',(take,uid,item['uid']));consumed.append(((item['group'],item['slot']),dict(item,count=item['count']-take)))
                            if not n:break
                    reward=q['Reward']
                    if any(reward.get(k,0) for k in ('m_iSP','m_iBuff','m_eChangeUnitClass')):raise ValueError('Unsupported native quest reward')
                    ep=reward.get('m_iEP',0)
                    from els_server.storage.ep_points import credit as credit_ep
                    credit_ep(db,uid,ep)
                    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
                    plan=[]
                    for r in sequence(reward.get('m_vecItem',{}))+selection:
                        t=r['m_iItemID']
                        if r['m_iPeriod'] or r['m_sSocketOption'] or t not in VERIFIED_TEMPLATES:raise ValueError('Unverified native quest reward item')
                        plan.append(dict(template=t,metadata=VERIFIED_TEMPLATES[t],quantity=r['m_iQuantity'],group=TEMPLATE_BAG_GROUPS[t]))
                    awards=grant_items(db,plan,uid) if plan else []
                    ed,xp=reward['m_iED'],reward['m_iEXP']
                    if any(type(v) is not int or v<0 for v in (ed,xp)):raise ValueError('Quest reward balance')
                    db.execute('UPDATE reward_balances SET ed=ed+?,experience=experience+?,revision=revision+1 WHERE uid=?',(ed,xp,uid))
                    if xp:
                        from els_server.game_data import client_data
                        experience=db.execute('SELECT experience FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0]
                        level=client_data().level_for_experience(experience)
                        db.execute('UPDATE characters SET level=?,revision=revision+1 WHERE uid=? AND level<?',(level,uid,level))
                    from els_server.storage.artifact_progression import complete_quest as complete_artifact_quest
                    complete_artifact_quest(db,uid,qid)
                    db.execute('DELETE FROM character_quests WHERE owner=? AND quest=?',(uid,qid))
                    saved_reward=dict(ed=ed,experience=xp,items=awards,consumed_positions=[pos for pos,_ in consumed])
                    if selection:saved_reward['selected_templates']=[r['m_iItemID'] for r in selection]
                    if ep:saved_reward['ep']=ep
                    db.execute('INSERT INTO completed_quests VALUES (?,?,?,?)',(uid,qid,now,json.dumps(saved_reward,sort_keys=True)))
                    from els_server.storage.epic_followups import accept_after_reward
                    accept_after_reward(db,uid,qid,load_character(db,uid,self.account_id),load_items(db,uid),location,now)
                db.execute('INSERT INTO quest_actions VALUES (?,?,?,?)',(operation_id,uid,kind,digest))
            items=load_items(db,uid);character=load_character(db,uid,self.account_id);state=_state(db,uid,items)
            if kind=='claim' and replayed:
                saved=db.execute('SELECT reward_json FROM completed_quests WHERE owner=? AND quest=?',(uid,qid)).fetchone()
                if saved:
                    saved=json.loads(saved[0]);ids={i['uid'] for i in saved['items']}
                    awards=[i for i in items if i['uid'] in ids]
                    consumed=[(tuple(pos),next((i for i in items if (i['group'],i['slot'])==tuple(pos)),None)) for pos in saved.get('consumed_positions',[])]
            from els_server.storage.reward_state import validate_balances
            balances=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(uid,)).fetchone())
            result=dict(replayed=replayed,state=state,character=character,balances=balances,items=items,updates=awards,consumed=consumed,slots=current_slots(db,character))
            # All responses, including full unit and inventory bodies, must be
            # encodable before SQL commit. No stale receipt inventory deltas.
            result['events']=encode(result)
            if not isinstance(result['events'],list) or any(not isinstance(e.payload,bytes) or len(e.payload)>65536 for e in result['events']):raise ValueError('Quest response bound')
            return result

    def record(self,event_id,event,proof):
        if not isinstance(event_id,str) or not 1<=len(event_id)<=200 or not isinstance(proof,bytes) or not proof:raise ValueError('Quest progress evidence')
        if event.get('kind') not in ('kill','clear','visit_town','visit_dungeon') or type(event.get('dungeon')) is not int or type(event.get('level')) is not int:raise ValueError('Quest progress event')
        if event['kind']=='kill' and type(event.get('npc')) is not int:raise ValueError('Quest NPC event')
        if event['kind']=='visit_town' and type(event.get('town')) is not int:raise ValueError('Quest town event')
        digest=hashlib.sha256(proof).hexdigest();raw=json.dumps(event,sort_keys=True)
        roll_proof=progress_proof(self.uid,event_id,proof)
        with closing(sqlite3.connect(self.path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE');load_character(db,self.uid,self.account_id);ensure(db)
            old=db.execute('SELECT proof_hash,event_json FROM quest_progress_events WHERE owner=? AND event_id=?',(self.uid,event_id)).fetchone()
            if old:
                if old!=(digest,raw):raise ValueError('Conflicting quest progress retry')
                return []
            state=_state(db,self.uid,load_items(db,self.uid));changed=[]
            for row in state['active']:
                counts=dict(row['objectives'])
                for s in quest_catalog().objectives(row['id']):
                    i=s['m_iID'];counts[i]=min(target(s),counts[i]+objective_increment(s,event,roll_proof))
                if counts!=row['objectives']:
                    db.execute('UPDATE character_quests SET objectives=? WHERE owner=? AND quest=?',(json.dumps(counts,sort_keys=True),self.uid,row['id']));changed.append(dict(row,objectives=counts))
            from els_server.protocol.quest_messages import progress
            events=[progress(changed)] if changed else []
            # Passive observations may run before a rejected request. Do not
            # create audit receipts for idle/no-task town or discovery polls.
            if not changed and event['kind'] in ('visit_town','visit_dungeon'):return []
            db.execute('INSERT INTO quest_progress_events VALUES (?,?,?,?)',(self.uid,event_id,digest,raw))
            return events
