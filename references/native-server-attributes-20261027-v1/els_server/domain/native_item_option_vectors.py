"""Fresh original7EBC80/7EB0D0 option vectors from canonical33 wire groups.

An explicit empty mutation map is required: the current server item writer
leaves that separate legacy map empty. Existing instance mutations must be
qualified before this fresh-constructor projection can be used for them.
"""

DIRECT=((0,0x60),(1,0x78),(2,0xa0),(3,0xb8),(4,0xd0),
        (5,0xe8),(6,0x100),(7,0x118),(8,0x130),(13,0x168),
        (17,0x1a8),(25,0x218),(26,0x248),(27,0x2a8),
        (29,0x2c0),(31,0x200),(32,0x2f8))


def project(groups,option_types,*,mutations):
    if type(groups)is not tuple or len(groups)!=33:
        raise ValueError('All33 ordered canonical option groups required')
    if type(mutations)is not tuple or mutations:
        raise ValueError('Fresh native constructor requires qualified empty mutation map')
    for row in groups:
        if type(row)is not tuple or any(type(v)is not int or not 0<=v<2**31 for v in row):
            raise ValueError('Canonical nonnegative int32 option IDs required')
    if len(groups[28])>16:raise ValueError('Original circuit vector capacity exceeded')
    result={offset:groups[group]for group,offset in DIRECT}
    result[0x190]=groups[14:17]
    result[0x158]={group:groups[group]for group in(9,10,11,12,22,23,24)}
    selected=next((group for group in(18,19,20,21)if groups[group]),None)
    result[0x1c8]=groups[selected]if selected is not None else ()
    result[0x1e0]=selected
    result[0x1e8]=tuple(v for v in groups[1]if option_types.get(v)in(803,804,805,806))
    result[0x2d8]=groups[28]+(0,)*(16-len(groups[28]))
    return result
