"""Original +5% boost adaptation: finite native maps, template and factor."""
import struct

DUNGEONS=frozenset((34810,34820,34830,34840,35410,35420,35430,35440))
TEMPLATE=3345
FACTOR=3518
DURATION=9999

def world_row(owner,row):
    if(row.get('_boosting')is not True or row['owner']!=owner or row['template']!=TEMPLATE
        or any(type(row[k])is not int for k in('start','end'))
        or not 1<=row['start']<row['end']<2**31 or row['end']-row['start']>DURATION):
        raise ValueError('Invalid native boost buff row')
    return bytes(8)+struct.pack('>iIQfBif?if?iiiQQ',TEMPLATE,0,owner,0.,1,0,0.,False,FACTOR,1.,False,-1,0,0,row['start'],row['end'])
