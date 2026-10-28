"""867440 category gates over explicit original option order and traversal.

Four-bin inputs require at least4 resolved options, all of one nonzero color.
Missing option records remain None and are ignored by this family only.
"""
from els_server.domain.native_dynamic_sets import property_value,ordered_color,color_four

def qualifies(row,category):
    if category in(1,2,3):return color_four(row['four_groups'])!=0
    if category in(9,10,11):
        return property_value(row['properties'],0x3c)==2 and ordered_color(row['color3c'])!=0
    if category in(12,13,14):
        if not any(prop[0]==0x50 for prop in row['properties']):return False
        colors=row['circuit_colors']
        if type(colors)is not tuple:raise ValueError('qualified B32630 traversal colors required')
        if not colors or any(color is None for color in colors):return False
        if any(type(color)is not int or not 0<=color<2**32 for color in colors):raise ValueError('uint32 option colors required')
        return colors[0]!=0 and all(color==colors[0]for color in colors)
    return True
