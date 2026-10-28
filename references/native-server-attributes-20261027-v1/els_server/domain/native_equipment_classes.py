"""Original8A20E0 family, branch and stage gate over pinned native arrays."""
from functools import lru_cache
import hashlib,json
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT

SOURCE_SHA256='9215b85f214307fe0447a414ff2f9ed48e6dce2fe64a551186d9961a147cf9a5'


@lru_cache(maxsize=1)
def tables():
    raw=(PROJECT_ROOT/'references/native-server-attributes-20261027-v1/native-equipment-classes.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:
        raise ValueError('Qualified original equipment class arrays required')
    values=json.loads(raw)['rows']
    if set(values)!={str(i)for i in range(206)}:
        raise ValueError('Complete original class array range required')
    return MappingProxyType({int(k):MappingProxyType(v)for k,v in values.items()})


def class_eligible(required,current):
    if type(required)is not int or type(current)is not int:
        raise ValueError('Explicit original class identities required')
    if required==0:return True
    rows=tables()
    if required not in rows or current not in rows:
        raise ValueError('Unqualified original equipment class')
    a,b=rows[required],rows[current]
    return a['family']==b['family']and(a['branch']==0 or a['branch']==b['branch'])and b['stage']>=a['stage']
