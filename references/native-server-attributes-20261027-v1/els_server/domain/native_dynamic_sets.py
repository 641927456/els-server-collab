"""6CAB20 dynamic set selection, with source-order colors and explicit gaps.

Caller supplies resolved original option colors, retaining None for missing
records. Circuit colors must come from qualified B32630 traversal, not all16
slots. This module never decides whether an item is worn/eligible/activated.
"""
def property_value(rows,key,slot=1):
    if slot not in (1,2,3):return -1
    result=-1
    for row in rows:
        if type(row) is not tuple or len(row)!=6 or any(type(v)is not int or not 0<=v<2**32 for v in row):raise ValueError('six original property words required')
        if row[0]==key:
            result=row[slot+1]
            if result>=2**31:result-=2**32
    return result

def color_four(groups):
    if type(groups)is not tuple or len(groups)!=4:raise ValueError('four original color vectors required')
    colors=[v for group in groups for v in group if v is not None]
    if any(type(v)is not int or not 0<=v<=3 for v in colors):raise ValueError('native four-bin color bound')
    if len(colors)>=4 and colors and colors[0] in (1,2,3) and all(v==colors[0] for v in colors):return colors[0]
    return 0

def ordered_color(colors):
    if type(colors)is not tuple:raise ValueError('original ordered color vector required')
    selected=0
    for value in colors:
        if value is None:continue
        if type(value)is not int or not 0<=value<2**32:raise ValueError('uint32 option color required')
        if selected and selected!=value:return 0
        selected=value
    return selected

def derive_set_id(base,properties,*,four_groups=((),(),(),()),color43=(),color3c=(),circuit_colors=None):
    if type(base)is not int or not 0<=base<2**32:raise ValueError('uint32 base set required')
    if base:return base
    if property_value(properties,0x35)!=-1:
        value=color_four(four_groups)
        return 0x18e6+value if value in (1,2,3) else 0
    if property_value(properties,0x43)!=-1:
        value=ordered_color(color43)
        return 0x2060+value if value in (1,2,3,4,5) else 0
    if property_value(properties,0x3c)==2:
        value=ordered_color(color3c)
        return 0x245d+value if value in (1,2,3) else 0
    if any(row[0]==0x50 for row in properties):
        if circuit_colors is None:raise ValueError('qualified original circuit traversal required')
        if type(circuit_colors)is not tuple:raise ValueError('explicit traversed circuit colors required')
        if not circuit_colors:return 0
        first=circuit_colors[0]
        return 0x4e23+first if first in (1,2,3) and all(v==first for v in circuit_colors) else 0
    return 0
