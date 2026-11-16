"""Current202 query and complete203 unavailable response, never a score provider."""
import struct
from els_server.protocol.protocol_codec import Event

# Pinned current ResultStringTable: 区域排行公告栏查询错误。
UNAVAILABLE=1168

def request(payload):
 if type(payload)is not bytes or len(payload)!=8:raise ValueError('Ranking original query length')
 return struct.unpack('>iI',payload)

def unavailable(category):
 if type(category)is not int or not -(2**31)<=category<2**31:raise ValueError('Ranking category wire bound')
 # Every original vector is present. No entries/pages are invented; the final
 # nonzero result distinguishes unavailable data from a successful empty list.
 return Event(0x201,kind=0x203,payload=struct.pack('>iII',category,0,0)+bytes(20*4)+struct.pack('>i',UNAVAILABLE))
