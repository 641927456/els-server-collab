"""Definition-based learning and upgrade rules for the local character service.

Free, unsealed character skills and the first Master grade auto-learn.
Relationship, core, guild, paid skill-point and sealed grades need unlocks.
"""
from els_server.game_data import client_data

ORDINARY_TYPES=frozenset((1,2,3,4,5,6,7,8,13,14,15,16))
ACTIVE_TYPES=frozenset((5,6,7,13,14,15,16,22,23,24,25))


def learned_skills(character):
    from els_server.domain.character_rules import CLASSES
    if character is None:character={'unit_class':1,'level':1}
    cls=character['unit_class'];level=character.get('level',1)
    if cls not in CLASSES or type(level) is not int or not 1<=level<=99:raise ValueError('Skill character identity')
    # Skill script stages include transcendence between second and third job.
    stage=CLASSES[cls]['stage']
    stage=4 if stage==3 else 3 if stage==2 and character.get('transcendence') else stage
    from els_server.domain.skill_unlocks import unsealed_skills
    unsealed=set(unsealed_skills(character))
    data=client_data();result={};deleted=set()
    for skill_id,master_level in data.skill_tree(cls):
        skill=data.skill(skill_id)
        if skill['m_eType'] not in ORDINARY_TYPES or (skill.get('m_bBornSealed') and skill_id not in unsealed):
            continue
        if skill.get('m_iRequireLearnSkillPoint',0) or skill.get('m_iRequireUpgradeSkillPoint',0):
            continue
        ranks=skill.get('m_RequireCharacterLevel',{})
        stages=skill.get('m_RequireUnitClassType',{})
        rank=0
        for candidate in range(1,master_level+1):
            required_level=ranks.get(str(candidate));required_stage=stages.get(str(candidate))
            if type(required_level) is not int or type(required_stage) is not int or required_level>level or required_stage>stage:break
            rank=candidate
        if rank:
            result[skill_id]=rank
            if skill.get('m_DeleteSkillIDByUpgrade'):deleted.add(skill['m_DeleteSkillIDByUpgrade'])
    from els_server.domain.role_progression import first_master_skill
    master=first_master_skill(character)
    if master:
        skill=data.skill(master)
        if level>=skill['m_RequireCharacterLevel']['1'] and not skill.get('m_bBornSealed'):
            result[master]=1
    from els_server.domain.role_progression import master_skills
    for skill in master_skills(cls):
        if skill in unsealed:result[skill]=1
    return {key:value for key,value in result.items() if key not in deleted}


def equippable_skills(character):
    data=client_data()
    return tuple(s for s in learned_skills(character) if data.skill(s)['m_eType'] in ACTIVE_TYPES)


def upgraded_slots(slots, character):
    """Follow explicit upgrade edges; retain layout without granting other jobs."""
    data=client_data();allowed=set(equippable_skills(character))
    replacements={}
    for skill_id in allowed:
        old=data.skill(skill_id).get('m_DeleteSkillIDByUpgrade')
        if old:replacements[old]=skill_id
    out=[]
    from els_server.domain.role_progression import catalog,first_master_skill,slot_accepts
    master_ids={sid for grades in catalog()['master_skills'].values() for sid in grades.values()}
    for index,skill in enumerate(slots):
        if skill in master_ids and skill not in allowed:
            grade=data.skill(skill)['m_eType']-22
            candidates=catalog()['master_skills'].get(str(character['unit_class']),{}) if character else {}
            skill=candidates.get(str(grade),0)
            if skill not in allowed:skill=first_master_skill(character) if character else 0
        seen=set()
        while skill in replacements:
            if skill in seen:raise ValueError('Cyclic skill upgrade')
            seen.add(skill);skill=replacements[skill]
        out.append(skill if skill in allowed and skill not in out and slot_accepts(index,skill) else 0)
    return tuple(out)
