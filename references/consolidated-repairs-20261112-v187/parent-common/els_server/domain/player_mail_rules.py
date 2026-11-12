"""Ordinary mail fee arithmetic recovered from pinned 2DE7620/2DDB1E0."""
import struct


def _f32(value):
    return struct.unpack('<f',struct.pack('<f',value))[0]


def fee(ed, *, price=0, quantity=0):
    if (type(ed) is not int or not 0<=ed<=70_000_000_000
            or type(price) is not int or not 0<=price<2**31
            or type(quantity) is not int or not 0<=quantity<=99):
        raise ValueError('Mail fee input bound')
    factor=_f32(.05)
    money=int(_f32(_f32(ed)*factor))
    item=int(_f32(_f32(_f32(_f32(price)*_f32(.2))*factor)*_f32(quantity)))
    return 200+money+item
