"""Original ordered groups for two exact current mixed story tasks.

Legacy CheckCompleteSubQuest_BeforGroup requires every earlier group member
to have succeeded before the current member can progress. These two tasks
contain no collection exceptions and keep their original source groups.
"""
GROUPS={22168:((22192,),(22193,),(22194,)),22206:((22246,),(22247,22248),(22249,22250))}


def validate(quest):
    identity=quest.get('m_iID')
    if identity not in GROUPS:return False
    groups=GROUPS[identity]
    expected={str(n):{'0':None,**{str(k):sid for k,sid in enumerate(group,1)}} for n,group in enumerate(groups,1)}
    flat=tuple(sid for group in groups for sid in group)
    subs={'0':None,**{str(n):sid for n,sid in enumerate(flat,1)}}
    if quest['m_vecSubQuest_Group']!=expected or quest['m_vecSubQuest']!=subs:
        raise ValueError('Mixed story exact original ordered subquest groups')
    return True


def can_progress(quest,sub,counts):
    if quest.get('m_iID') not in GROUPS:return True
    validate(quest)
    groups=GROUPS[quest['m_iID']]
    flat={sid for group in groups for sid in group}
    if set(counts)!=flat or sub.get('m_iID') not in flat:
        raise ValueError('Mixed story saved objective identity')
    earlier=[]
    for group in groups:
        if sub['m_iID'] in group:
            # All targets in these exact visit/find/clear/kill groups are one.
            return all(type(counts[sid]) is int and counts[sid]==1 for sid in earlier)
        earlier.extend(group)
    raise ValueError('Mixed story current group')
