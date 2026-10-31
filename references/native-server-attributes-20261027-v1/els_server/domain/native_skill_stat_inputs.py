"""Original9BFE30 m_Stat rows; ownership and channel selection are separate."""
from els_server.domain.native_power_kernel import f32

FIELDS=((6,'m_BaseHP'),(7,'m_AtkPhysic'),(8,'m_AtkMagic'),
        (11,'m_DefPhysic'),(12,'m_DefMagic'))


def load(definition):
    data=definition.get('m_Stat')
    if data is None:
        return ()
    if type(data) is not dict:
        raise ValueError('Original m_Stat source table required')
    vectors={}
    for slot,key in FIELDS:
        raw=data.get(key,{})
        if raw is None:
            raw={}
        if type(raw) is not dict:
            raise ValueError('Original one-based source vector required')
        keys=set(raw)-{'0'}
        if keys!={str(n) for n in range(1,len(keys)+1)}:
            raise ValueError('Contiguous one-based source vector required')
        vectors[slot]=tuple(f32(raw[str(n)]) for n in range(1,len(keys)+1))
    count=max(map(len,vectors.values()))
    return tuple(tuple(vectors[slot][n] if slot in vectors and n<len(vectors[slot])
                       else f32(0.) for slot in range(13)) for n in range(count))
