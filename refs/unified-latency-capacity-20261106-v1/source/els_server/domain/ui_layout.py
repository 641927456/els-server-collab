"""HUD record shared by native 196ab60 (load) and 19b8ca0 (save)."""
import struct

RECORD=struct.Struct('>iQ9hBh')
# Initial reference-canvas arrangement, checked visually in the client.
# The final four zeros request the native text-widget default branch.
DEFAULT_LAYOUT=(422,644,360,675,1,700,100,0,0,0,0)

def validate_layout(values):
    if len(values)!=11:raise ValueError('Invalid HUD field count')
    if any(not isinstance(v,int) or not -32768<=v<=32767 for v in values):
        raise ValueError('Invalid HUD short')
    # Preserve signed coordinates, including native -1 sentinels. A zero or
    # negative scale would collapse the HUD; its field is a signed percentage.
    if not 0<values[6]<=1000 or values[9] not in (0,1):raise ValueError('Invalid HUD scale or bool')
    if values[10] not in (0,*range(10,31)):raise ValueError('Invalid HUD font size')
    return tuple(values)

def decode_layout(payload):
    if len(payload)!=RECORD.size:raise ValueError('Invalid HUD payload size')
    result,uid,*values=RECORD.unpack(payload)
    if result!=0 or uid not in (0,1001):raise ValueError('Invalid local HUD identity')
    return validate_layout(values)

def encode_layout(values):
    return RECORD.pack(0,0,*validate_layout(values))
