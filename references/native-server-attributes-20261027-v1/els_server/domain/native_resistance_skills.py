"""Original860290's four qualified current skill contributions, source order."""
from els_server.domain.native_passive_attributes import f32,parameter

SKILLS=((26401,'SA_FIRE_DEFENCE_ABS',True,True),
        (28405,'SA_FIRE_DEFENCE_ABS',True,False),
        (30409,'SA_EL_DEFENCE_ABS',False,True),
        (23401,'ENCHANT_DEFENCE',False,True))


def values(definitions,ranks,*,pvp):
    if type(pvp)is not bool or type(ranks)is not dict or set(ranks)!={r[0]for r in SKILLS}:
        raise ValueError('Explicit original four skill ranks and phase mode required')
    out=[f32(0.)]*6
    for sid,name,direct,all_six in SKILLS:
        rank=ranks[sid]
        if type(rank)is not int or not 0<=rank<=255:
            raise ValueError('Original positive-byte queried rank required')
        if not rank:continue
        source=definitions[sid]
        if source.get('m_eID')!=sid:raise ValueError('Original skill definition identity differs')
        value=parameter(source,name,rank,pvp=pvp,direct=direct,default=0.)
        for i in(range(6)if all_six else(0,)):out[i]=f32(out[i]+value)
    return tuple(out)
