"""Current original PVPData coefficients used by rank-linked item options."""
from functools import lru_cache
import hashlib,json
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT
from els_server.domain.native_power_kernel import f32

SOURCE_SHA256='073121694ce93e43cd7b0ad11a14bb3387aac0d4d33739ab86f57255d0942763'


@lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'references/native-server-attributes-20261027-v1/native-rank-coefficients.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:
        raise ValueError('Qualified current PVPData coefficients required')
    source=json.loads(raw)
    if set(source['rows'])!={str(v)for v in range(11)}:
        raise ValueError('Complete original rank registry required')
    return MappingProxyType({int(k):f32(v)for k,v in source['rows'].items()})


def coefficient(rank):
    """FF1150: registered none/arrange both1; absent int8 keys return0."""
    if type(rank)is not int or not -128<=rank<=127:
        raise ValueError('Explicit native signed-byte rank source required')
    return catalog().get(rank,0.)
