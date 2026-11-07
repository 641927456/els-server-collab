"""Owned native-window host, not a game process or a player session."""
import ctypes,hashlib,json,pathlib,struct,sys
image=pathlib.Path(sys.argv[1]).read_bytes()
assert hashlib.sha256(image).hexdigest()=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.VirtualAlloc.restype=ctypes.c_void_p
kernel.VirtualAlloc.argtypes=(ctypes.c_void_p,ctypes.c_size_t,ctypes.c_ulong,ctypes.c_ulong)
base=kernel.VirtualAlloc(0x140000000,0x5000000,0x3000,0x40)
assert base==0x140000000
manager=kernel.VirtualAlloc(None,0x2000,0x3000,0x04);assert manager
ctypes.memmove(base+0x4817e70,struct.pack('<Q',manager),8)
for start,end in((0x2378760,0x237876e),(0x22262ee,0x22262fb)):
    ctypes.memmove(base+start,image[start:end],end-start)
# Replace the two GUI continuations in this private host with boolean returns.
ctypes.memmove(base+0x22262fb,b'\x31\xc0\xc3',3)
ctypes.memmove(base+0x22264cf,b'\xb8\x01\0\0\0\xc3',6)
wrapper=b'\x53\x48\x83\xec\x20\x89\xcb\xe8'+struct.pack('<i',0x22262ee-0x100c)+b'\x48\x83\xc4\x20\x5b\xc3'
ctypes.memmove(base+0x1000,wrapper,len(wrapper))
call=ctypes.WINFUNCTYPE(ctypes.c_int,ctypes.c_int)(base+0x1000)
print(json.dumps(dict(ready=True,base=hex(base),owned_native_window=True)),flush=True)
for line in sys.stdin:
    command=json.loads(line)
    if command=='exit':break
    expected,current=command;ctypes.c_int.from_address(manager+0x1040).value=current
    print(json.dumps(dict(result=call(expected))),flush=True)
