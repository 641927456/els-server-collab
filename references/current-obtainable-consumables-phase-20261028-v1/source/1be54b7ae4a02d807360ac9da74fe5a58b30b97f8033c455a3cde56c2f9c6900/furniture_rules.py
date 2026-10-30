"""136039 literal contents and four existing native furniture definitions only."""
from functools import lru_cache
import hashlib,json
TEMPLATE=136039
POLICY='current-small-furniture-original-description-20261028-v1'
# Original HousingItemTemplet.lua SHA6602935c.. plus complete19803A0 bag25.
ROWS=((570011,1,'3e408bd59de5ffcaf917c78f42b011f5cabde54b497f78049565b689f970b7e8'),
      (570012,1,'486579e5048a672101a1e83a977a01dd6c84a666e25e29a97a012fd5b23c7751'),
      (570015,2,'a529b3f1046791cbb2fb4d02d87d1968c4d039fdec07c164b9c7d5225ab000fe'),
      (570016,1,'f4494fc59d92bffa2d63a71750276007dd299083d296255d42c6c03dc43b04d9'))
TEMPLATES=frozenset(t for t,n,h in ROWS)
POSITION_TYPES={570011:(2,3),570012:(2,3),570015:(5,6),570016:(4,)}

@lru_cache(maxsize=1)
def definitions():
 from els_server.game_data import client_data,CLIENT_SHA
 c=client_data()
 if CLIENT_SHA!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709':raise ValueError('Furniture native build')
 if hashlib.sha256(c.item(TEMPLATE)['record']).hexdigest()!='0567ac6833f56ac2722e347d7b0cd8b2d5d5ed6df70b3f71baaf0c53ea273398':raise ValueError('Furniture box original definition')
 for t,n,h in ROWS:
  item=c.item(t)
  if(item['metadata'],item['item_type'])!=(0,16)or hashlib.sha256(item['record']).hexdigest()!=h:raise ValueError('Furniture original child definition')
 return tuple(dict(template=t,quantity=n,metadata=0,group=25)for t,n,h in ROWS)

def plan():return[dict(r)for r in definitions()]

def authorize_output(template,source):
 if template not in TEMPLATES or source is None:return False
 from els_server.domain.raid_reward_items import validate_source
 source=validate_source(source);identity=json.loads(source._source)
 if(source.kind!='box'or identity.get('policy')!=POLICY or identity.get('template')!=TEMPLATE
    or identity.get('owner')!=source.owner or type(identity.get('uid'))is not int or identity['uid']<=0):raise ValueError('Furniture exact owned-box source')
 source.validate_plan(plan());return True

def validate_layout(layout,items,*,mutating=False,now=None):
 from els_server.protocol.housing_layout_messages import LAYOUT,encode
 from els_server.domain.item_expiration import require_current
 from els_server.domain.item_locks import require_unlocked
 encode(LAYOUT,layout)
 legacy,new,grid,floor,expansion=layout
 #This batch has only the original unexpanded first floor/preset.
 if floor!=0 or expansion not in(-1,0):raise ValueError('Furniture unqualified room expansion')
 owned={i['uid']:i for i in items if i['template']in TEMPLATES and i['metadata']==0 and i['group']==25 and i['count']==1}
 used=set();skins=set()
 for modern,rows in((False,legacy),(True,new)):
  for key,value in rows:
   if modern:uid,t,position,xyz,direction=value;level=0
   else:position,uid,t,x,y,direction=value;xyz=(x,y,0);level=0
   if key!=uid or uid in used or uid not in owned or owned[uid]['template']!=t:raise ValueError('Furniture unique owned UID/template')
   item=owned[uid];require_current(item,now=now)
   if mutating:require_unlocked(item,now=now)
   if item.get('sealed',False)or position not in POSITION_TYPES[t]or level!=0:raise ValueError('Furniture native placement kind')
   #Same bounded finite coordinates as current native housing readiness.
   #Client-native geometry/collision keeps its original coordinate convention.
   if any(abs(v)>1000000 for v in xyz):raise ValueError('Furniture position bounds')
   if position in(4,5,6):
    if position in skins:raise ValueError('Duplicate furniture surface skin')
    skins.add(position)
   used.add(uid)
 if len(used)>36:raise ValueError('Furniture local bag allowance')
 cells=0
 for kind,rows in grid:
  if not 0<=kind<=7 or len(rows)>128 or any(len(row)>128 for row in rows):raise ValueError('Furniture grid bounds')
  for row in rows:
   cells+=len(row)
   if cells>8192 or any(v not in used and v not in(0,2**64-1)for v in row):raise ValueError('Furniture foreign grid reference')
 return layout
