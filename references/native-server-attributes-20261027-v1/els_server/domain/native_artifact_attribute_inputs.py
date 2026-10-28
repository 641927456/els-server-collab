"""Master Artifact options from original 8A34C9..8A365F, without mutation."""
from functools import lru_cache
from types import MappingProxyType
import hashlib,json
from els_server.paths import PROJECT_ROOT

SOURCE_SHA256='8edb3d843a0988b271937e08d233676fc328b5005cfb86e6c4d90d2986406736'
TEMPLATE_SHA256='33eaea3e7200aef5f37054004400be781757a9e9de75a813051e5ee8c94543c3'

def decode(raw):
    if type(raw)is not bytes or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:
        raise ValueError('Qualified original Artifact source required')
    value=json.loads(raw)
    if (value['schema']!=1 or value['source_sha256']!=TEMPLATE_SHA256
            or set(value['definitions'])!={str(i)for i in range(1,16)}):
        raise ValueError('Original Artifact source coverage differs')
    return MappingProxyType({int(k):tuple(tuple(g)for g in groups)for k,groups in value['definitions'].items()})

@lru_cache(maxsize=1)
def catalog():
    return decode((PROJECT_ROOT/'references/native-server-attributes-20261027-v1/native-artifact-attribute-sources.json').read_bytes())

def option_ids(template,evolution,potentials):
    if (type(template)is not int or type(evolution)is not int or not 0<=evolution<=5
            or type(potentials)is not tuple or len(potentials)!=4
            or any(type(v)is not int or not 0<=v<2**31 for v in potentials)):
        raise ValueError('Complete original Artifact stage/potential inputs required')
    if not template:
        if evolution or any(potentials):raise ValueError('Absent Artifact has nonempty source')
        return ()
    groups=catalog()[template];result=[]
    for group in groups[:evolution]:result.extend(group)
    if evolution>=3:
        # Original mutates its copied fourth word at stages3/4. Preserve the
        # SQL snapshot and return the equivalent ordered option vector.
        result.extend(potentials[:3]);result.append(potentials[3]if evolution>=5 else 0)
    return tuple(result)
