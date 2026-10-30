"""Current canonical character skill sources for original Unit stat queries.

Actor action-skill bonuses are a separate consumer. Owning a Force book does
not make its passive rank effective; the canonical visible three slots do.
"""


def passive_ranks(visible_slots,skill_types):
    if type(visible_slots)is not tuple or len(visible_slots)!=11:
        raise ValueError('Complete canonical visible Force layout required')
    result={}
    for index,pair in enumerate(visible_slots):
        if type(pair)is not tuple or len(pair)!=2 or any(type(v)is not int for v in pair):
            raise ValueError('Canonical Force identity/rank pair required')
        sid,rank=pair
        if pair==(0,0):continue
        if not 0<sid<2**31 or not 0<rank<=255:
            raise ValueError('Canonical Force int32/byte source required')
        if index>=3:continue
        if skill_types[sid]!=17 or sid in result:
            raise ValueError('Distinct currently selected type17 passive required')
        result[sid]=rank
    return result


def from_character(character):
    from els_server.domain.skill_rules import learned_skills
    from els_server.domain.boosting_2026_force_equipment import slots
    from els_server.game_data import client_data
    visible=slots(character,visible=True)
    kinds={sid:client_data().skill(sid)['m_eType']for sid,rank in visible[:3]if sid}
    ordinary=learned_skills(character);forces=passive_ranks(visible,kinds)
    if set(ordinary)&set(forces):raise ValueError('Native source channel collision')
    return dict(ordinary)|forces
