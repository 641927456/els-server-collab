"""Finite ordinary-route hunter boxes, explicit20261024 local source policy.

Modern pool/weights/spawn chance are local choices. XP and grade cutoffs reuse
the indexed old70 same action. No generic class101 or ordinary death producer.
"""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import hashlib,struct
from els_server.domain.hunter_sphere_rules import STEPS,definitions
from els_server.protocol.profession_messages import ProfessionState,state_wire

POLICY='hunter-chest-local-20261024-v1'
SOURCE_ROUTES={30282: (37, '3da2896f31f56f9f1c1239455bd40dbab24c87b46b63409ca6e47a54f956ca5d'), 33202: (70, 'c5c13300ddb677fa274194036820b79be46c5f19b1c406e17f01497175344fa2'), 33232: (72, '2ad86a70dc61c61d3df3dbeaccf3d09fb2253b99a7db57242eb214a514bbe365'), 33252: (77, 'f8fcbe09cad35b426a3221cff7173febb0acb457eea3ab57296c53d391df248e'), 34320: (99, 'b6905a338e4919afc3445aecf999828b6476bfccfe223bda084019998595021c')}
NAMES={1615: ['破旧的宝物箱', '破旧的宝物箱', 'Old_Treasure_Box.lua', '', '', ''], 1616: ['木质宝物箱', '木质宝物箱', 'Wooden_Treasure_Box.lua', '', '', ''], 1617: ['石质宝物箱', '石质宝物箱', 'Stone_Treasure_Box.lua', '', '', ''], 1618: ['华丽的宝物箱', '华丽的宝物箱', 'Splendid_Treasure_Box.lua', '', '', ''], 1619: ['发光的宝物箱', '发光的宝物箱', 'Shining_Treasure_Box.lua', '', '', '']}
POOLS={1615:((117527,70),(118204,15),(118205,15)),
       1616:((117527,50),(117528,20),(118204,15),(118205,15)),
       1617:((117527,35),(117528,30),(118092,5),(118204,15),(118205,15)),
       1618:((117528,40),(118092,20),(118204,20),(118205,20)),
       1619:((117528,30),(118092,30),(118204,20),(118205,20))}
XP={1615:10,1616:20,1617:30,1618:60,1619:100}

def grade(level):
 if type(level)is not int or not 1<=level<=99:raise ValueError('Hunter current dungeon max level')
 return 1615+sum(level>cut for cut in (20,35,50,65))

def reward(template,roll):
 definitions()
 if type(template)is not int or template not in POOLS or type(roll)is not int or not 0<=roll<100:raise ValueError('Hunter pool/RNG')
 for item,weight in POOLS[template]:
  roll-=weight
  if roll<0:return dict(template=item,metadata=2,group=4 if item in (117527,117528,118092)else 3,quantity=1)
 raise ValueError('Hunter pool mass')

def advance(state,template):
 state_wire(state)
 if state.profession!=1 or not 1<=state.level<=10:raise ValueError('Hunter saved state')
 # Unknown old denominators retain their save and item eligibility; no fake XP.
 if state.level==10 or state.required<=0 or state.progress>=state.required:return state,0
 delta=min(XP[template],state.required-state.progress+sum(STEPS[n]for n in range(state.level+1,10)))
 if state.experience+delta>=2**31:raise ValueError('Hunter XP overflow')
 level,progress,required=state.level,state.progress+delta,state.required
 while level<10 and progress>=required:
  progress-=required;level+=1;required=STEPS.get(level,0)
 if level==10:progress=required=0
 result=replace(state,level=level,experience=state.experience+delta,progress=progress,required=required)
 state_wire(result);return result,delta

def week(now):
 if type(now)not in (int,float) or not 0<=now<2**40:raise ValueError('Hunter time bound')
 local=datetime.fromtimestamp(now,timezone(timedelta(hours=8)))
 reset=local.replace(hour=10,minute=0,second=0,microsecond=0)-timedelta(days=(local.weekday()-2)%7)
 if local<reset:reset-=timedelta(days=7)
 return int(reset.timestamp())

def digest(value):
 import json
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def ground_templates():
 definitions()
 return frozenset((117527,117528,118092,118204,118205))
