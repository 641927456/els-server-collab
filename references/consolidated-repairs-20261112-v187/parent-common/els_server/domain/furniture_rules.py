"""Native quest furniture and the literal contents of furniture box136039."""
from functools import lru_cache
import hashlib,json
TEMPLATE=136039
POLICY='current-small-furniture-original-description-20261028-v1'
NPC_POLICY='current-native-npc-furniture-20261108-v1'
# Original HousingItemTemplet.lua SHA6602935c.. plus complete19803A0 bag25.
ROWS=((570011,1,'3e408bd59de5ffcaf917c78f42b011f5cabde54b497f78049565b689f970b7e8'),
      (570012,1,'486579e5048a672101a1e83a977a01dd6c84a666e25e29a97a012fd5b23c7751'),
      (570015,2,'a529b3f1046791cbb2fb4d02d87d1968c4d039fdec07c164b9c7d5225ab000fe'),
      (570016,1,'f4494fc59d92bffa2d63a71750276007dd299083d296255d42c6c03dc43b04d9'))
QUEST_ROWS=((570001,1,'45d7cb71efd809c65074c829fe39b2659d2dd61b64c84ecc4486453133c38937'),
            (570002,1,'1802831e66fa89cefef4697b85e01e4943427b4983b246d53a238a0564f02270'),
            (570014,1,'ac89ab80b5c70ed2fa5f45e89b2c2207aac01faef98918b5edd3b10a5c9aea4d'))
BOX_TEMPLATES=frozenset(t for t,n,h in ROWS)
QUEST_TEMPLATES=frozenset(t for t,n,h in QUEST_ROWS)
SHOP_ROWS=(
 (570003,1,'f9308a8bdc4f76e78882bc36d543be01036e549f2d1aa1f9f4cb24b74cc3bef1'),
 (570004,1,'15506a567117b80ba7201316c9bc30d8c5fd1ac6ec2b31e4f59c683fa7bc7801'),
 (570005,1,'df755bf0d4b1954006170198f67b6007a3cf13ebb0c2c1f7e2372927db625ce1'),
 (570006,1,'1fb1ea5c1ee813851e13e9e0885cf3c1fa32eddc5df2a935c746ce6395fd58a7'),
 (570007,1,'bc222f92dfe61534c8e9f7d325a2ffa59592991502a7df43a06fb05e201351a2'),
 (570008,1,'680bd5a5b3d0c0fe780284ddd57094c9a4655bc88844b892af8a918432c3dd4d'),
 (570009,1,'d612f538fe71b01b8d6133e2b0840f4937a4e8472a569d5b73075b4b5c8bdea3'),
 (570010,1,'26946644b42222e01d68fe16ae6a7b68d2dca0d56edae979409ac82dcb82686a'),
 (570013,1,'b496680acdf59c7f3877724715771ef2ca0f68949754319b82f6739179453d8d'),
)
SHOP_TEMPLATES=frozenset(t for t,n,h in SHOP_ROWS)
NPC_TEMPLATES=BOX_TEMPLATES|SHOP_TEMPLATES
from els_server.domain.housing_pet_rules import ROWS as PET_ROWS,TEMPLATES as PET_TEMPLATES,mat
TEMPLATES=NPC_TEMPLATES|QUEST_TEMPLATES|PET_TEMPLATES
# Original usable location1 maps to floor1; wall2 maps to left/right2/3.
# Native skin surfaces retain their separate position4/5/6 distinction.
POSITION_TYPES={570001:(1,),570002:(1,),570014:(1,),570011:(2,3),570012:(2,3),570015:(5,6),570016:(4,)}

POSITION_TYPES.update({t:(1,)for t in PET_TEMPLATES|SHOP_TEMPLATES})
LEGACY_FLOOR_POSITION_TEMPLATES=QUEST_TEMPLATES|PET_TEMPLATES

@lru_cache(maxsize=1)
def definitions():
 from els_server.game_data import client_data,CLIENT_SHA
 c=client_data()
 if CLIENT_SHA!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709':raise ValueError('Furniture native build')
 if hashlib.sha256(c.item(TEMPLATE)['record']).hexdigest()!='0567ac6833f56ac2722e347d7b0cd8b2d5d5ed6df70b3f71baaf0c53ea273398':raise ValueError('Furniture box original definition')
 for t,n,h in ROWS+QUEST_ROWS+PET_ROWS+SHOP_ROWS:
  item=c.item(t)
  if(item['metadata'],item['item_type'])!=(0,16)or hashlib.sha256(item['record']).hexdigest()!=h:raise ValueError('Furniture original child definition')
 return tuple(dict(template=t,quantity=n,metadata=0,group=25)for t,n,h in ROWS+QUEST_ROWS+PET_ROWS+SHOP_ROWS)

def plan():return[dict(r)for r in definitions()if r['template']in BOX_TEMPLATES]

def authorize_output(template,source):
 if template not in NPC_TEMPLATES or source is None:return False
 from els_server.domain.raid_reward_items import validate_source
 source=validate_source(source);identity=json.loads(source._source)
 if source.kind=='npc_trade':
  from els_server.domain.npc_trade import stock
  town,merchant=identity.get('town'),identity.get('merchant')
  if template in SHOP_TEMPLATES and (town not in range(20000,20014) or merchant!=10018):
   raise ValueError('Basic furniture requires Ariel in an ordinary village')
  if(identity.get('policy')!=NPC_POLICY or identity.get('owner')!=source.owner
     or identity.get('operation')!=source.operation
     or template not in stock().get((town,merchant),())):raise ValueError('Furniture exact native merchant source')
  source.validate_template(template)
  return True
 if(template not in BOX_TEMPLATES or source.kind!='box'or identity.get('policy')!=POLICY or identity.get('template')!=TEMPLATE
    or identity.get('owner')!=source.owner or type(identity.get('uid'))is not int or identity['uid']<=0):raise ValueError('Furniture exact owned-box source')
 source.validate_plan(plan());return True

def validate_layout(layout,items,*,mutating=False,now=None,legacy_floor_locations=False):
 from els_server.protocol.housing_layout_messages import LAYOUT,encode
 from els_server.domain.item_expiration import require_current
 from els_server.domain.item_locks import require_unlocked
 encode(LAYOUT,layout)
 legacy,new,grid,reserved,floor=layout
 if reserved!=0 or not 0<=floor<=2:raise ValueError('Furniture native floor fields')
 owned={i['uid']:i for i in items if i['template']in TEMPLATES and i['metadata']==0 and i['group']==25 and i['count']==1}
 used=set();skins=set()
 for modern,rows in((False,legacy),(True,new)):
  for key,value in rows:
   if modern:uid,t,position,xyz,direction=value;level=0
   else:
    position,uid,t,x,y,item_floor=value;xyz=(x,y,0);level=0
    if item_floor!=floor:raise ValueError('Furniture record floor differs from layout')
   if key!=uid or uid in used or uid not in owned or owned[uid]['template']!=t:raise ValueError('Furniture unique owned UID/template')
   # Original244D4A0 applies grid furniture through2451350 and binds
   # Game+B00 to its pet mat.244D960 free-position records create a model
   # without this binding, so accepting a pet mat there cannot spawn pets.
   if modern and t in PET_TEMPLATES:raise ValueError('Housing pet mats require native grid placement')
   item=owned[uid];require_current(item,now=now)
   if mutating:require_unlocked(item,now=now)
   legacy_position=legacy_floor_locations and not mutating and floor==0 and t in LEGACY_FLOOR_POSITION_TEMPLATES and position in(2,3)
   if item.get('sealed',False)or(position not in POSITION_TYPES[t]and not legacy_position)or level!=0:raise ValueError('Furniture native placement kind')
   #Same bounded finite coordinates as current native housing readiness.
   #Client-native geometry/collision keeps its original coordinate convention.
   if any(abs(v)>1000000 for v in xyz):raise ValueError('Furniture position bounds')
   if position in(4,5,6):
    if position in skins:raise ValueError('Duplicate furniture surface skin')
    skins.add(position)
   used.add(uid)
 mat(layout)
 from els_server.domain.bag_capacity import FURNITURE_CAPACITY
 if len(used)>FURNITURE_CAPACITY:raise ValueError('Furniture bag allowance')
 cells=0
 for kind,rows in grid:
  if not 0<=kind<=7 or len(rows)>128 or any(len(row)>128 for row in rows):raise ValueError('Furniture grid bounds')
  for row in rows:
   cells+=len(row)
   if cells>8192 or any(v not in used and v not in(0,2**64-1)for v in row):raise ValueError('Furniture foreign grid reference')
 return layout
