"""Original 21F request and 220 result: selected template, not material UID."""
import struct
from els_server.domain.fashion_state import record,empty_record

def request(payload):
 if not isinstance(payload,bytes) or len(payload)!=13:raise ValueError('Restoration request size')
 uid,template,profession=struct.unpack('>QiB',payload)
 if not 1<=uid<2**63 or profession!=0:raise ValueError('Unsupported restoration identity or profession')
 from els_server.domain.advanced_enhancement_materials import restoration_templates
 if template not in restoration_templates():raise ValueError('Unsupported restoration scroll')
 return uid,template

def acknowledgement(ed=0,*,result=0,changes=()):
 # 2282044 reads result; 228209E reads vector<original inventory row>.
 return struct.pack('>iI',result,len(changes))+b''.join(empty_record(*p) if item is None else record(item) for p,item in changes)
