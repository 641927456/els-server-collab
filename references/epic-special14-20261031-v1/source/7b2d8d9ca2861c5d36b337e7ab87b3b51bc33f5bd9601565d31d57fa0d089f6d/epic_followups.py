"""Continue admitted current story edges after a committed parent reward.

The legacy CheckEpicQuest_NewQuestByAfterQuest supplies the flow contract;
identities, conditions and objectives come exclusively from the pinned build.
This accepts tasks only. It never completes an objective or grants a reward.
"""
import hashlib,json
from els_server.domain.seal_quests import quest_catalog,sequence,require_eligible,ACTIVE_QUEST_LIMIT


def _accepted_generation(db,uid,parent,identity,quest,now):
    """Keep the same owner/action generation guard used by manual NPC accept.

    The parent reward and its current after-edge have already been checked.
    These are server automatic acceptance receipts, not client talk events.
    They commit/roll back with the parent reward or restore snapshot.
    """
    from els_server.domain.town_dialogue import catalog as town_catalog
    definition=town_catalog()['quests'].get(str(identity))
    from els_server.domain.mainline_find_npc import catalog as find_catalog
    finite_find=identity in find_catalog()['quest_ids']
    if definition is None and not finite_find:return now
    if definition is not None and quest!=definition:raise ValueError('Automatic NPC task source changed')
    if finite_find and quest!=quest_catalog().quest(identity):raise ValueError('Automatic FindNPC task source changed')
    operation=f'epic-after:{uid}:{parent}:{identity}'
    if db.execute('SELECT 1 FROM quest_actions WHERE operation_id=?',(operation,)).fetchone():
        # Active/completed tasks are skipped before reaching here. An orphan
        # prior acceptance must not silently become a new accepted generation.
        raise ValueError('Automatic NPC accept receipt without current task')
    digest=hashlib.sha256(json.dumps([uid,'accept',dict(quest=identity,npc=0)],sort_keys=True).encode()).hexdigest()
    cursor=db.execute('INSERT INTO quest_actions VALUES (?,?,?,?)',(operation,uid,'accept',digest))
    generation=cursor.lastrowid
    if type(generation) is not int or not 0<generation<2**63:raise ValueError('Automatic NPC acceptance generation')
    return generation


def accept_after_reward(db,uid,parent,character,items,location,now,*,excluded=()):
    catalog=quest_catalog()
    source=catalog.quest(parent)
    if source['m_eQuestType']!=5:return ()
    if not db.execute('SELECT 1 FROM completed_quests WHERE owner=? AND quest=?',(uid,parent)).fetchone():
        raise ValueError('Story continuation requires committed parent reward')
    completed={r[0] for r in db.execute('SELECT quest FROM completed_quests WHERE owner=?',(uid,))}
    active={r[0] for r in db.execute('SELECT quest FROM character_quests WHERE owner=?',(uid,))}
    accepted=[]
    # Preserve source order and all alternatives; class/level/place conditions
    # select eligible branches. Missing definitions never become empty tasks.
    for identity in dict.fromkeys(sequence(source.get('m_iAfterQuestID',{}))):
        if len(active)>=ACTIVE_QUEST_LIMIT:break
        if identity in active or identity in completed or identity in excluded or identity==22164:continue
        quest=catalog.quests.get(identity)
        if quest is None or quest['m_eQuestType']!=5:continue
        if identity in (25610,25611,25612):continue  # Canonical account adapter owns expedition acceptance.
        if (quest.get('m_bIsPcBang') or quest.get('m_bIsTimeEvent') or quest.get('m_bRepeat')
            or quest.get('m_iRandomGroupID') or quest.get('CHANGE_JOB_TYPE')):continue
        try:
            require_eligible(character,quest,completed,items,location=location)
        except ValueError:
            continue
        counts={sub['m_iID']:0 for sub in catalog.objectives(identity)}
        # Reuse ordinary accept's already-proven current-town observation.
        for sub in catalog.objectives(identity):
            if sub['m_eClearType']==24 and location[0]=='town' and location[1] in sequence(sub['m_ClearCondition']['m_eVillageID']):
                counts[sub['m_iID']]=1
        generation=_accepted_generation(db,uid,parent,identity,quest,now)
        db.execute('INSERT INTO character_quests VALUES (?,?,?,?,?)',(uid,identity,now,generation,json.dumps(counts,sort_keys=True)))
        active.add(identity);accepted.append(identity)
    return tuple(accepted)


def restore_deferred(db,uid,character,items,location,now):
    """Recheck explicit admitted edges at login/validated town arrival.

    Only existing completion receipts supply parents. A delayed level, place
    or capacity requirement may now pass. The ordinary eligibility function
    still decides admission. Persisted manual abandon actions suppress repair;
    no task/reward migration or fabricated completion is performed.
    The caller owns the transaction and encodes its snapshot before commit.
    """
    catalog=quest_catalog()
    completed={r[0] for r in db.execute('SELECT quest FROM completed_quests WHERE owner=?',(uid,))}
    active={r[0] for r in db.execute('SELECT quest FROM character_quests WHERE owner=?',(uid,))}
    if len(active)>=ACTIVE_QUEST_LIMIT:return ()
    abandon_hashes={r[0] for r in db.execute("SELECT request_hash FROM quest_actions WHERE owner=? AND kind='abandon'",(uid,))}
    parents=[];excluded=set()
    for parent in sorted(completed):
        source=catalog.quests.get(parent)
        if source is None or source['m_eQuestType']!=5:continue
        missing=[i for i in sequence(source.get('m_iAfterQuestID',{}))
                 if i in catalog.quests and i not in completed and i not in active]
        if not missing:continue
        parents.append(parent)
        for identity in missing:
            digest=hashlib.sha256(json.dumps([uid,'abandon',dict(quest=identity)],sort_keys=True).encode()).hexdigest()
            if digest in abandon_hashes:excluded.add(identity)
    accepted=[]
    for parent in parents:
        accepted.extend(accept_after_reward(db,uid,parent,character,items,location,now,excluded=excluded))
    return tuple(accepted)


def deferred_write_possible(db,uid):
    """Conservative exclusion only; never authorizes a story acceptance.

    A possible child still goes through restore_deferred under the original
    writer, including all source, level, place, abandon and capacity checks.
    """
    catalog=quest_catalog()
    completed={r[0] for r in db.execute('SELECT quest FROM completed_quests WHERE owner=?',(uid,))}
    active={r[0] for r in db.execute('SELECT quest FROM character_quests WHERE owner=?',(uid,))}
    if len(active)>=ACTIVE_QUEST_LIMIT:return False
    for parent in completed:
        source=catalog.quests.get(parent)
        if source is None or source['m_eQuestType']!=5:continue
        if any(identity in catalog.quests and identity not in active and identity not in completed
               for identity in sequence(source.get('m_iAfterQuestID',{}))):return True
    return False
