"""B6ED11..B6EDF4 class attack-kind inputs for the native CP consumer.

Only the second-class relative-stat registry populates Game+668. Original
89B430 takes its missing-entry branch for base/first classes. Ties select2.
This classification is separate from the server's sourced naked growth rule.
"""
from functools import lru_cache
import hashlib,json
from types import MappingProxyType
from els_server.domain.native_power_kernel import f32

TABLE_SHA256='cf8525e3586d38eafce1d8c52adf34c9ff553c95ac58e450411c1a2f4ceb8f1b'


def project(table):
    if type(table)is not dict or ('0'in table and table['0']is not None):
        raise ValueError('Original one-based relative class table required')
    keys=set(table)-{'0'}
    if len(keys)>1024 or keys!={str(i)for i in range(1,len(keys)+1)}:
        raise ValueError('Complete ordered native relative class source required')
    result={}
    for i in range(1,len(keys)+1):
        row=table[str(i)]
        if type(row)is not dict:raise ValueError('Original relative class source row required')
        identity=row.get('1')
        if type(identity)is not int or not 0<identity<2**31 or identity in result:
            raise ValueError('Distinct current native class source required')
        physical=f32(row.get('2',0.));magical=f32(row.get('4',0.))
        result[identity]=2 if physical<=magical else 1
    return MappingProxyType(result)


@lru_cache(maxsize=1)
def catalog():
    from els_server.game_data import client_data
    source=client_data().resource('CharacterStatTable.lua')['SECOND_CLASS_RELATIVE_STAT_TABLE']
    if hashlib.sha256(json.dumps(source,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=TABLE_SHA256:
        raise ValueError('Native current class attack-kind source changed')
    return project(source)


def kind(class_id,definitions):
    if type(class_id)is not int or not 0<=class_id<2**31:
        raise ValueError('Explicit native current class identity required')
    return definitions.get(class_id)
