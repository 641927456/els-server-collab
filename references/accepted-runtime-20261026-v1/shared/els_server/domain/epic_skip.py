"""Original Epic skip admission/reward projection, not fabricated objectives.

3044530: Epic, level-FairLevel>5, not time-event, positive known After,
and FLAGS excludes NO_FREE_PASS. 3038ED0 copies item/selection rewards;
positive EXP becomes half and clears ED/EP/GuildHonorPoint. Zero-EXP
ED stays as the current native preview shows. EP is always zero, per the
current CN official guide, including the zero-EXP100810 source edge.
"""
from els_server.domain.seal_quests import sequence

WRITER_ENABLED=True

def requested(request):
    flags=request.get('flags',())
    return len(flags)==5 and flags[1]==1

def reward(character,quest,catalog):
    if not WRITER_ENABLED:raise ValueError('New Epic skips are held')
    fair=quest.get('m_iFairLevel');level=character['level'];flags=quest.get('FLAGS','')
    after=tuple(i for i in sequence(quest.get('m_iAfterQuestID',{})) if type(i) is int and i>0)
    if (quest.get('m_eQuestType')!=5 or quest.get('m_bIsTimeEvent')==1
        or type(fair) is not int or type(level) is not int or level-fair<=5
        or not isinstance(flags,str) or 'NO_FREE_PASS' in flags
        or not after or any(i not in catalog.quests for i in after)):
        raise ValueError('Epic skip source/level/After requirement')
    result=dict(quest['Reward']);xp=result['m_iEXP'];ed=result['m_iED']
    if any(type(v) is not int or v<0 for v in (xp,ed)):raise ValueError('Epic skip reward values')
    if xp>0:
        result['m_iEXP']=xp//2;result['m_iED']=0;result['m_iGuildHonorPoint']=0
    result['m_iEP']=0
    return result
