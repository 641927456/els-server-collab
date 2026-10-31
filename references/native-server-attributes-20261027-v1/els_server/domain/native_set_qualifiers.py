"""70FB30 unsigned maximum of the first word of qualified set triples.

This is the maximum threshold used by85E660's qualifier selection. It does
not itself select a set effect, count worn pieces or qualify a real item.
"""
def maximum_threshold(qualified):
    if qualified is None:return 0
    if type(qualified)is not tuple or len(qualified)>1024:raise ValueError('explicit qualified rows required')
    maximum=0
    for row in qualified:
        if type(row)is not tuple or len(row)!=3:raise ValueError('qualified triple required')
        first,key,effect=row
        if type(first)is not int or not -2**31<=first<2**31:raise ValueError('int32 source threshold required')
        if any(type(v)is not int or not 0<=v<2**32 for v in(key,effect)):raise ValueError('uint32 qualifier/effect required')
        maximum=max(maximum,first&0xffffffff)
    return maximum
