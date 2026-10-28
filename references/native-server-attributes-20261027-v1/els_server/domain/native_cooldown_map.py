"""OriginalB225D0 cooldown-category map producer, before988320 caps."""
from els_server.domain.native_power_kernel import f32

FIELDS=frozenset((0x418,0x390,0x394,0x398,0x39c))


def apply_cooldown_categories(scalars, existing):
    if type(scalars) is not dict or set(scalars)!=FIELDS:
        raise ValueError('All five native cooldown inputs required')
    if type(existing) is not dict or len(existing)>1024:
        raise ValueError('Explicit bounded existing map required')
    if any(type(k) is not int or not -2**31<=k<2**31 for k in existing):
        raise ValueError('Native int32 category key required')
    fields={k:f32(v)for k,v in scalars.items()}
    result={k:f32(v)for k,v in existing.items()}
    all_skills=fields[0x418]
    if all_skills!=0.:
        for key in(6,14,15,16):result[key]=f32(all_skills+result.get(key,0.))
    for offset,key in((0x390,6),(0x394,14),(0x398,15),(0x39c,16)):
        value=fields[offset]
        if value!=0.:result[key]=f32(value+result.get(key,0.))
    return result
