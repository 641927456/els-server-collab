"""Continue admitted current story edges after a committed parent reward.

The legacy CheckEpicQuest_NewQuestByAfterQuest supplies the flow contract;
identities, conditions and objectives come exclusively from the pinned build.
This accepts tasks only. It never completes an objective or grants a reward.
"""
import json
from els_server.domain.seal_quests import quest_catalog,sequence,require_eligible,ACTIVE_QUEST_LIMIT


def accept_after_reward(db,uid,parent,character,items,location,now):
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
        if identity in active or identity in completed:continue
        quest=catalog.quests.get(identity)
        if quest is None or quest['m_eQuestType']!=5:continue
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
        db.execute('INSERT INTO character_quests VALUES (?,?,?,?,?)',(uid,identity,now,now,json.dumps(counts,sort_keys=True)))
        active.add(identity);accepted.append(identity)
    return tuple(accepted)
