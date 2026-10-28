"""Exact 70F980 set-effect ID selection, after eligibility/count gathering.

The ordinary table selects the highest qualified threshold group, not every
lower threshold. The qualified table uses all matching signed-count rows.
This does not replace the separate867440 wear/side/activation eligibility.
"""
def uint32(value):
    if type(value) is not int or not 0<=value<2**32:raise ValueError('uint32 required')
    return value

def int32(value):
    if type(value) is not int or not -2**31<=value<2**31:raise ValueError('int32 required')
    return value

def select_effect_ids(ordinary,qualified,qualifier,pieces):
    uint32(qualifier);uint32(pieces)
    if type(ordinary) is not tuple or len(ordinary)>1024:raise ValueError('explicit ordinary rows required')
    last=-1
    for row in ordinary:
        if type(row) is not tuple or len(row)!=2:raise ValueError('threshold and effect ID required')
        threshold,effect=row;uint32(threshold);uint32(effect)
        if threshold<last:raise ValueError('original ordinary table must be ordered')
        last=threshold
    if qualified is not None:
        if type(qualified) is not tuple or len(qualified)>1024:raise ValueError('explicit qualified rows required')
        for row in qualified:
            if type(row) is not tuple or len(row)!=3:raise ValueError('count, qualifier and effect ID required')
            int32(row[0]);uint32(row[1]);uint32(row[2])
        signed_count=pieces if pieces<2**31 else pieces-2**32
        return tuple(effect for minimum,key,effect in qualified if qualifier and minimum<=signed_count and key==qualifier)
    eligible=[row for row in ordinary if row[0]<=pieces]
    if not eligible:return ()
    maximum=eligible[-1][0]
    return tuple(effect for threshold,effect in eligible if threshold==maximum)
