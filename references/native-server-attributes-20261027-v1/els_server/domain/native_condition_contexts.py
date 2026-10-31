"""Original896EB1..896F71 condition inputs from the preceding aggregate."""
from els_server.domain.native_power_kernel import f32
from els_server.domain.native_power_slopes import normalize


def build_condition_contexts(resistances, *, physical_defense, magical_defense,
                             physical_defense_rate, magical_defense_rate,
                             normalized_defense, normalized_additional,
                             experience_rate, precondition_skill_categories):
    if type(resistances) is not tuple or len(resistances)!=6:
        raise ValueError('Six original pre-condition resistance values required')
    values=tuple(map(f32,resistances))
    total=values[0]
    for index in(5,4,2,1,3):total=f32(total+values[index])
    physical=f32(physical_defense);magical=f32(magical_defense)
    physical_rate=f32(physical_defense_rate);magical_rate=f32(magical_defense_rate)
    physical=f32(f32(physical*physical_rate)+physical)
    magical=f32(f32(magical*magical_rate)+magical)
    defense=f32(magical+physical)
    reduction=f32(normalize(0x988180,f32(normalized_defense))*f32(100.))
    if type(precondition_skill_categories) is not dict or len(precondition_skill_categories)>1024:
        raise ValueError('Complete original pre-condition category map required')
    if any(type(key)is not int or not -2**31<=key<2**31 for key in precondition_skill_categories):
        raise ValueError('Original signed category keys required')
    categories={key:f32(value)for key,value in precondition_skill_categories.items()}
    # Unit3078 stores the copied map. B26140 reads its key13, not its pointer.
    return {0x3060:total,0x3064:reduction,0x3068:defense,
            0x306c:f32(normalized_additional),0x3070:f32(experience_rate),
            0x3078:categories.get(13,0.)}
