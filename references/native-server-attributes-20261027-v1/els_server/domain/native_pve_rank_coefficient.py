"""Original PVEData normal/MP registries and865660 source-key selection."""
from functools import lru_cache
import hashlib,json
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT
from els_server.domain.native_power_kernel import f32

SOURCE_SHA256='652b4133b215b631626310a91d2532514447f0c2ff7945c4473837c832291e80'


@lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'references/native-server-attributes-20261027-v1/native-pve-rank-coefficients.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:
        raise ValueError('Qualified current PVEData registries required')
    source=json.loads(raw)
    if set(source['rows'])!={'0','1'}or any(set(v)!={str(i)for i in range(10)}for v in source['rows'].values()):
        raise ValueError('Complete two original PvE registries required')
    return tuple(MappingProxyType({int(k):f32(v)for k,v in source['rows'][str(flag)].items()})for flag in(0,1))


def coefficient(rank,*,for_mp):
    if type(rank)is not int or not -128<=rank<=127 or type(for_mp)is not bool:
        raise ValueError('Explicit original signed-byte rank and MP selector required')
    # FF1500 compares an MP-table miss with the normal table header. Only the
    # registered current MP input domain is qualified; never fabricate its miss.
    if for_mp and not 0<=rank<=9:raise ValueError('Unqualified original MP rank key')
    return catalog()[int(for_mp)].get(rank,0.)


def factor(definition,*,stage,grade,first_count,second_count):
    from els_server.domain.native_option_scalar_inputs import scalar_inputs
    if any(type(v)is not int or not -2**31<=v<2**31 for v in(stage,first_count,second_count)):
        raise ValueError('Original signed32 PvE stage/count context required')
    if type(grade)is not int or not -128<=grade<=127:raise ValueError('Original signed-byte PvE grade required')
    total=(first_count+second_count+2**31)%2**32-2**31
    key=0 if stage<3 or stage==3 and total==0 else grade
    fields=scalar_inputs(definition);a=fields[0x180];b=fields[0x188]
    return coefficient(key,for_mp=a>0. and a==b)
