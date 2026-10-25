"""DX11 creation: native C67780/C67B00 writers and 2B4C620 reader."""
import struct
from els_server.protocol.local_messages import i32,u32,wstring,character_unit
from els_server.protocol.protocol_codec import Event

# Current native C1C340 handles these ResultStringTable entries explicitly.
NAME_TAKEN=0x14a
NAME_INVALID=0x14d
NAME_LENGTH=0x14e

def creation_error(error):
    message=str(error)
    if message=='Character name already exists':return NAME_TAKEN
    if message in ('Character name length','Character name wire length'):return NAME_LENGTH
    if isinstance(error,UnicodeError) or message in ('Character name characters','Noncanonical character name','Missing character name'):
        return NAME_INVALID
    return 1

def _name(payload,offset=0):
    if len(payload)<offset+4:raise ValueError('Missing character name')
    length=struct.unpack_from('>I',payload,offset)[0];offset+=4
    if length%2 or not 4<=length<=24 or offset+length>len(payload):raise ValueError('Character name wire length')
    return payload[offset:offset+length].decode('utf-16le'),offset+length

def name_request(payload):
    # C67780: int server, UTF16 name.
    if len(payload)<8:raise ValueError('Name request length')
    server=struct.unpack_from('>i',payload)[0];name,end=_name(payload,4)
    if server!=1 or end!=len(payload):raise ValueError('Name request server/trailing data')
    return name

def create_request(payload):
    # C67B00 + DB1910: name, type, server, byte, byte, map<int,int>.
    name,pos=_name(payload)
    if len(payload)<pos+14:raise ValueError('Create request length')
    base_class,server,flag,mode,count=struct.unpack_from('>iiBBI',payload,pos);pos+=14
    # C16560 uses the class -> BASE CLASS table 48A1BE0. Later characters
    # send 200..205 here, not UNIT_TYPE 10..15.
    from els_server.storage.characters import BASE_CLASSES
    types={value:key for key,value in BASE_CLASSES.items()}
    if base_class not in types:raise ValueError('Invalid base character class')
    unit_type=types[base_class]
    if server!=1 or flag not in (0,1) or mode not in (0,1) or count>32 or len(payload)!=pos+8*count:
        raise ValueError('Create request options')
    options=dict(struct.unpack_from('>ii',payload,pos+i*8) for i in range(count))
    if len(options)!=count:raise ValueError('Duplicate create option')
    return dict(name=name,unit_type=unit_type,flag=flag,mode=mode,options=options)

def name_ack(name,result=0):
    # C1C340: result, Q, string. The Q is unused on the normal path.
    return Event(0x201,kind=0x48c,payload=i32(result)+struct.pack('>Q',0)+wstring(name))

def create_ack(character,result=0,items=None,location=None):
    # 2B4C620: result, full D9B170 unit, vector<int>, string, int,
    # three bools, string, int, three bools, Q,Q,int,Q,Q.
    tail=u32(0)+wstring('')+i32(0)+bytes(3)+wstring('')+i32(-1)+bytes(3)+bytes(16)+i32(0)+bytes(16)
    return Event(0x201,kind=0x25,payload=i32(result)+character_unit(location=location,economy={'ed':0,'experience':0},items=items or [],character=character)+tail)
