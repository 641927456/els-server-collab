"""Strict679 ordinary type1 224; original fullrecord primitive, no type3 change."""
import struct
from els_server.domain.fashion_state import record, empty_record


def acknowledgement(ed, changes=(), rewards=(), result=0):
    if type(ed) is not int or not 0 <= ed < 2**63 or type(result) is not int or result not in (0,-1):
        raise ValueError('Recipe679 absoluteED/result')
    if not isinstance(changes,(list,tuple)) or len(changes)>72:
        raise ValueError('Recipe679 full vector bound')
    if not isinstance(rewards,(list,tuple)) or list(rewards) not in ([],[(119335,1)]):
        raise ValueError('Recipe679 single historical result')
    if (result == -1 and (changes or rewards)) or (result == 0 and list(rewards) != [(119335,1)]):
        raise ValueError('Recipe679 result profile')
    seen, uids, rows = set(), set(), []
    for position,item in changes:
        if (type(position) is not tuple or len(position)!=2
                or any(type(v) is not int for v in position)
                or not 0<=position[0]<=255 or not 0<=position[1]<=32767 or position in seen):
            raise ValueError('Recipe679 changed position')
        seen.add(position)
        if item is None:
            rows.append(empty_record(*position))
        else:
            if (item['group'],item['slot']) != position or item['uid'] in uids:
                raise ValueError('Recipe679 changed currentUID')
            uids.add(item['uid']); rows.append(record(item))
    result_map = b''.join(struct.pack('>ii',t,n) for t,n in rewards)
    return (struct.pack('>iI',result,len(changes)) + b''.join(rows)
            + struct.pack('>I',len(rewards)) + result_map
            + struct.pack('>BBQQ',1,1,0,ed))
