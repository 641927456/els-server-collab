"""Original89C6D0 multiplies coefficients for distinct activated set IDs.

Keep binary64 source values and native sorted-set iteration. This factor is
computed afresh, not a persisted or client-reported character power value.
"""
from functools import lru_cache
import hashlib,json,math
from collections.abc import Mapping
from types import MappingProxyType
from els_server.paths import PROJECT_ROOT

SOURCE_SHA256='591086db53db5c6a6887f6826cf6ef6e5609b152701f8e4b97d5228fd425a8a2'


def decode(raw):
    if type(raw)is not bytes or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:
        raise ValueError('Qualified native set-power source required')
    data=json.loads(raw)
    if data.get('schema')!=1 or len(data['rows'])!=3:
        raise ValueError('Current native set-power registry differs')
    values={}
    for identity,value in data['rows']:
        if type(identity)is not int or not 0<identity<2**31 or identity in values:
            raise ValueError('Distinct current set-power source IDs required')
        if type(value)not in(int,float)or not math.isfinite(value):
            raise ValueError('Finite original binary64 set-power value required')
        values[identity]=float(value)
    return MappingProxyType(values)


@lru_cache(maxsize=1)
def catalog():
    return decode((PROJECT_ROOT/'references/native-server-attributes-20261027-v1/native-set-power-factor-sources.json').read_bytes())


def factor(active_ids,definitions):
    if type(active_ids)is not tuple or len(active_ids)>16384 or not isinstance(definitions,Mapping):
        raise ValueError('Complete qualified native active-set IDs and coefficient map required')
    if any(type(v)is not int or not -2**31<=v<2**31 for v in active_ids):
        raise ValueError('Native signed active-set key required')
    value=1.
    for identity in sorted(set(active_ids)):
        coefficient=definitions.get(identity,1.)
        if type(coefficient)not in(int,float)or not math.isfinite(coefficient):
            raise ValueError('Finite original binary64 set-power coefficient required')
        value*=float(coefficient)
        if not math.isfinite(value):raise ValueError('Native set-power overflow')
    return value


def active_sets(pieces,definitions):
    from els_server.domain.native_set_conditions import select_effect_ids
    if type(pieces)is not dict or len(pieces)>16384 or not isinstance(definitions,Mapping):
        raise ValueError('Complete qualified native set counts and templates required')
    active=[]
    for identity,(qualifier,count)in sorted(pieces.items()):
        if type(identity)is not int or not 0<=identity<2**31:
            raise ValueError('Qualified current native set ID required')
        definition=definitions.get(identity)
        if definition is not None and select_effect_ids(definition['ordinary'],definition['qualified'],qualifier,count):
            # The original inserts before individual effect entry gates.
            active.append(identity)
    return tuple(active)
