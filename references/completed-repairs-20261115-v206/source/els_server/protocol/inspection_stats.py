"""Validate the original DB4880/D9EE90 public stat map without recomputing it."""
import math
import struct

MAX_BYTES=32768
# Scalar runs and collections in the pinned D9EE90 reader's exact wire order.
SHAPE=(25,'map','map',18,'vector',14,'pair_map',44)


def validate(raw,*,luciel=False):
    if not isinstance(raw,bytes)or not 0<len(raw)<=MAX_BYTES:
        raise ValueError('Inspected stat map size')
    offset=0
    def read(fmt):
        nonlocal offset
        field=struct.Struct('>'+fmt)
        if offset+field.size>len(raw):raise ValueError('Truncated inspected stat map')
        value=field.unpack_from(raw,offset);offset+=field.size
        return value
    def count():
        value,=read('I')
        if value>256:raise ValueError('Inspected stat collection size')
        return value
    entries,=read('I')
    expected={0,1,2,3}if luciel else{0,2}
    if entries!=len(expected):raise ValueError('Inspected stat forms/modes')
    scores={}
    for _ in range(entries):
        key,=read('i')
        if key not in expected or key in scores:raise ValueError('Inspected stat key')
        start=offset
        for part in SHAPE:
            if isinstance(part,int):
                if not all(math.isfinite(v)for v in read(str(part)+'f')):
                    raise ValueError('Nonfinite inspected stat')
            else:
                seen=set()
                for _ in range(count()):
                    if part=='vector':read('i');continue
                    if part=='map':identity,value=read('if')
                    else:
                        number,flag,value=read('iBf')
                        if flag not in(0,1):raise ValueError('Inspected stat map flag')
                        identity=(number,flag)
                    if identity in seen or not math.isfinite(value):raise ValueError('Inspected stat map entry')
                    seen.add(identity)
        combat,defense=struct.unpack_from('>ff',raw,start)
        if any(not 0<=v<=4294967040 for v in(combat,defense)):
            raise ValueError('Inspected score range')
        scores[key]=(combat,defense)
    if offset!=len(raw):raise ValueError('Trailing inspected stat bytes')
    return scores
