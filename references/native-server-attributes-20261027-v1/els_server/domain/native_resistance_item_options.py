"""Original8623B0 main/secondary resistance option source order.

Inputs are already selected owned items. The old D0 capacity decision and
circuit weights are supplied by their own producers; this consumer must never
borrow the ordinary power collector's different source order or eligibility.
"""
from els_server.domain.native_power_kernel import f32


def collect(vectors,properties,template_options,*,secondary,allow4,allow26,
            allow27,allow_circuit,circuit_options,circuit_state):
    if any(type(v)is not bool for v in(secondary,allow4,allow26,allow27,allow_circuit)):
        raise ValueError('Explicit original resistance source activation required')
    if type(circuit_state)is not int or not 0<=circuit_state<2**32:
        raise ValueError('Original circuit state required')
    if type(properties)is not tuple or any(type(row)is not tuple or len(row)!=6
            or any(type(v)is not int or not 0<=v<2**32 for v in row)for row in properties):
        raise ValueError('Original complete property rows required')
    def ids(values):
        if type(values)is not tuple or any(type(v)is not int or not 0<=v<2**31 for v in values):
            raise ValueError('Ordered original option IDs required')
        return values
    result=[(identity,1.)for identity in ids(template_options)]
    def append(offset):result.extend((identity,1.)for identity in ids(vectors[offset]))
    for offset in(0x60,0x78,0xa0,0xb8,0x168):append(offset)
    if secondary:
        # Master Artifact equipment has a distinct, shorter source path.
        # 1C8/200 are unconditional here; neither is a main-item source.
        for offset in(0x1c8,0x200):append(offset)
        return tuple(result)
    if allow4:append(0xd0)
    for offset in(0xe8,0x100,0x118,0x130):append(offset)
    groups=vectors[0x158]
    if any(type(key)is not int for key in groups):raise ValueError('Original ordered option map required')
    for key in sorted(groups):result.extend((identity,1.)for identity in ids(groups[key]))
    for offset in(0x1a8,0x218):append(offset)
    present={row[0]for row in properties}
    if 0x4a in present and allow26:append(0x248)
    if 0x4e in present and allow27:append(0x2a8)
    if 0x52 in present:append(0x2c0)
    if type(circuit_options)is not tuple:raise ValueError('Qualified ordered circuit options required')
    if 0x50 in present and allow_circuit:
        for identity,weight in circuit_options:
            ids((identity,));result.append((identity,f32(weight)))
    if 0x59 in present and circuit_state:append(0x2f8)
    return tuple(result)
