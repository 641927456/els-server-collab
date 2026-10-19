"""Bounds for the recovered native purchase codec, not transaction acceptance."""
import struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shop_messages import PurchaseRequest,purchase_request,purchase_ack

one=bytes.fromhex('0000000100012345000200ffffffff')
assert purchase_request(one)==PurchaseRequest(((0x12345,2),),False,-1)
two=struct.pack('>IIHIHBi',2,10,1,20,65535,1,123)
assert purchase_request(two)==PurchaseRequest(((10,1),(20,65535)),True,123)
bad=[b'',one[:-1],one+b'\0',bytes(9),struct.pack('>I',0xffffffff)+bytes(5),
     struct.pack('>IIHBi',1,0,1,0,-1),struct.pack('>IIHBi',1,1,0,0,-1),
     struct.pack('>IIHBi',1,1,1,2,-1),struct.pack('>IIHIHBi',2,1,1,1,1,0,-1)]
for payload in bad:
    try:purchase_request(payload)
    except ValueError:pass
    else:raise AssertionError(payload.hex())
assert purchase_ack(-1).payload==bytes.fromhex('ffffffff0000000000000000000000')
assert purchase_ack(0,((0x12345,2),)).payload==bytes.fromhex('000000000000000100012345000200000000000000')
print('PASS: native purchase codec boundaries; transaction routing intentionally not enabled.')
