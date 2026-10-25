"""Original per-item +7..+10 gauge and +12 guarantee points."""
LIMITS={7:50,8:90,9:180,10:270}
# Official 2024-01-31 and 2026-09-09 notices. Original 7EB0D0 maps
# DTO 3A8/3AC -> real item 260/264, read by 23E94C0 for the UI.
def validate(item):
 from els_server.domain.normal_equipment import definitions
 gauge=item.get('enhancement_gauge',0);points=item.get('enhancement_guarantee',0);level=abs(item.get('enhancement',0))
 if item['template'] not in definitions() or item.get('count')!=1 or type(gauge) is not int or type(points) is not int or not 0<=gauge<=LIMITS.get(level,0) or not 0<=points<=(20 if level<12 else 0):raise ValueError('Invalid original enhancement progress')
 return gauge,points

def full(item):
 gauge,points=validate(item);level=item.get('enhancement',0)
 return level in LIMITS and gauge==LIMITS[level] or level==11 and points==20

def after(item,mode,result,updated):
 gauge,points=validate(item);level=item.get('enhancement',0)
 if mode==1 and 7<=level<=10:gauge=min(LIMITS[level],gauge+1)
 if abs(updated)!=level:gauge=0
 if mode==2 and level==11 and result==4 and updated==10:points=min(20,points+1)
 if abs(updated)>=12:points=0
 return gauge,points
