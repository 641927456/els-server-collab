"""204/205 layout verified with private parsers and isolated native networking."""
import struct
from enum import IntEnum
from els_server.domain.fashion_state import record,empty_record


class EnchantResult(IntEnum):
    UNKNOWN=1
    INVALID_STATE=2
    UNKNOWN_CHARACTER=10
    ITEM_NOT_OWNED=459
    NOT_ALLOWED=460
    OCCUPIED_SLOT=461
    EMPTY_SLOT=462
    INSUFFICIENT_ED=463
    INSUFFICIENT_CRYSTALS=464
    INVALID_ITEM=465
    INVALID_EQUIPMENT=466
    INSUFFICIENT_REMOVE_ED=658


class EnchantRejected(ValueError):
    def __init__(self,result):
        from els_server.result_messages import result_messages
        self.result=int(EnchantResult(result))
        super().__init__(result_messages().text(self.result))


def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=10:raise ValueError('Enchant request length')
    uid,slot,target=struct.unpack('>QBB',payload)
    if not 0<uid<2**63 or slot>=4 or target>7:raise ValueError('Enchant request fields')
    return uid,slot,target


def acknowledgement(ed,changes=(),result=0):
    if type(ed) is not int or not 0<=ed<2**63:raise ValueError('Enchant ED balance')
    if type(result) is not int or not -(2**31)<=result<2**31:raise ValueError('Enchant result')
    if not isinstance(changes,(list,tuple)) or len(changes)>256:raise ValueError('Enchant inventory vector')
    positions=set();records=[]
    for position,item in changes:
        if (not isinstance(position,tuple) or len(position)!=2 or
            any(type(n) is not int for n in position) or
            not 0<=position[0]<=255 or not 0<=position[1]<32768 or position in positions):
            raise ValueError('Enchant inventory position')
        positions.add(position)
        if item is not None and position!=(item['group'],item['slot']):raise ValueError('Enchant inventory position mismatch')
        records.append(empty_record(*position) if item is None else record(item))
    # These four fields are read but not used by 2E87920. Their original
    # server meaning remains unknown. Zero passed isolated native networking;
    # that does not establish their meaning for other operations or versions.
    return struct.pack('>iQQiBBI',result,ed,0,0,0,0,len(records))+b''.join(records)
