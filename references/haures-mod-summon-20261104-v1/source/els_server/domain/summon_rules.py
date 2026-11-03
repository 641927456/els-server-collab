"""Verified player-NPC producers in the pinned DX11 client.

Source: nisha-summons-20261101-v1/variants-v2 and variants-v3. These rules
authorize entity kinds, not casts, damage, timers or passive proc chances.
The original client continues to select parameters and execute those states.
Each requirement group needs one learned skill, including its upgrade family.
"""
from els_server.domain.skill_rules import learned_skills
from els_server.game_data import client_data

# templates, required skill groups, required equipped change skill, scene
RULES = (
    ((384,), ((25000,),), 0, None),
    ((2957,), ((33046,),), 0, None),
    ((2958,), ((33067,),), 0, None),
    ((2959,), ((33074,),), 0, None),
    ((2960,), ((33077,),), 0, None),
    ((2961,), ((33078,),), 0, None),
    ((1621,), ((25015,25236,25079),), 0, None),
    ((1622,), ((25020,25236,25079),), 0, None),
    ((1454,), ((25601,25604),), 0, None),
    ((1575,), ((22020,),), 0, None),
    ((2969,), ((22094,),), 0, 'pvp'),
    ((1635,), ((28018,),), 0, None),
    ((1641,), ((28023,28057,28090,28094),), 0, None),
    ((2967,), ((21245,),), 0, None),
    ((2175,2194), ((31002,),), 0, None),
    ((2208,), ((31413,),), 0, None),
    ((2206,), ((31044,),), 0, None),
    ((2209,), ((31045,),), 0, None),
    ((2211,), ((31047,),), 0, None),
    ((2956,), ((31049,),), 911030, None),
    ((2214,), ((31607,31608),), 0, None),
    ((2397,2952), ((31055,),), 0, None),
    ((2955,), ((31055,),), 911025, None),
    ((2398,), ((31059,),), 0, None),
    ((2526,), ((31096,),), 0, None),
    ((1908,), ((30016,),), 0, None),
    ((2269,), ((30053,),), 0, None),
    ((2954,), ((30053,),), 910016, None),
    ((1906,), ((30013,),), 0, 'pve'),
    ((1937,), ((30013,),), 0, 'pvp'),
    ((2948,), ((30013,),), 910001, 'pve'),
    ((2949,), ((30013,),), 910001, 'pvp'),
    ((2973,), ((30435,),), 0, None),
    ((1576,1577), ((29003,),), 0, None),
    ((5189,5190), ((29039,),), 0, None),
    ((5188,), ((29041,),), 0, None),
    ((2963,2964), ((29077,),), 0, None),
    ((1604,), ((29601,29604),), 0, None),
    ((2965,), ((809011,),), 0, None),
    ((2966,), ((809012,),), 0, None),
    ((863,1419), ((26014,26025),), 0, None),
    ((1100,), ((26083,),), 0, None),
    ((2976,), ((26097,),), 0, None),
    ((2527,), ((32009,),), 0, None),
    ((2975,), ((32244,),), 0, None),
    ((2970,2971), ((24431,),(24438,)), 0, None),
    ((2974,), ((28103,),), 0, None),
    ((2951,), ((28421,),), 0, None),
)
PLAYER_SUMMON_TEMPLATES = frozenset(t for templates, _, _, _ in RULES for t in templates)


def player_summon_templates(character, scene='pve'):
    if not character:
        return frozenset()
    data = client_data()
    if data.unit(character['unit_class'])['unitType'] != character['unit_type']:
        raise ValueError('Summon character class/type mismatch')
    known = set(learned_skills(character))
    # learned_skills intentionally removes the old ID on upgrade. The native
    # skill factories can still refer to that base ID, so follow explicit edges.
    for skill in tuple(known):
        old = data.skill(skill).get('m_DeleteSkillIDByUpgrade')
        while old and old not in known:
            known.add(old)
            old = data.skill(old).get('m_DeleteSkillIDByUpgrade')
    eligible = [(templates, force) for templates, groups, force, mode in RULES
                if mode in (None, scene) and all(known.intersection(g) for g in groups)]
    equipped = set()
    if any(force for _, force in eligible):
        from els_server.domain.boosting_2026_force_equipment import slots
        equipped = {skill for skill, rank in slots(character, visible=True)[3:] if skill}
    return frozenset(t for templates, force in eligible if not force or force in equipped
                     for t in templates)
