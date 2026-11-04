"""Generated finite-oracle checks for CFG joins and typed NPC identity provenance."""
import random,unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'source/tools'))
from npc_spawn_source_flow import Flow
class NPC:
 def __init__(self):self.number={};self.integer={};self.created=[]
 def SetNumber_LUA(self,key,value):self.number[key]=value
 def SetInt_LUA(self,key,value):self.integer[key]=value
 def GetNumber_LUA(self,key):return self.number[key]
 def CreateNPCReq_LUA(self,target,*args):self.created.append(target)
def fixture(a,b,accidental):
 keys=['SetNumber_LUA','SetInt_LUA','GetNumber_LUA','CreateNPCReq_LUA','NPC_UNIT_ID','ALPHA','BETA']
 code=[(26,31,2,0)] # Boolean before numeric 1 catches Python bool/int CSE aliasing.
 def put(method,key,value,enum=False):
  code.extend([(12,5,2,0),(65,3,keys.index(method),2),(24,6,key,0)])
  if enum:code.extend([(62,7,4,0),(65,7,keys.index(value),7)])
  else:code.append((24,7,value,0))
  code.append((46,3,4,1))
 put('SetNumber_LUA',0,'ALPHA',True);put('SetNumber_LUA',1,'BETA',True);put('SetNumber_LUA',2,accidental);put('SetInt_LUA',0,accidental)
 code.extend([(10,0,0,0),(88,0,2,128),(24,6,0,0),(88,0,1,128),(24,6,1,0)])
 code.extend([(12,5,2,0),(65,3,2,2),(46,3,3,2),(12,10,2,0),(65,8,3,2),(12,11,3,0),(24,12,99,0),(26,13,2,0),(24,14,0,0),(26,15,2,0),(24,16,0,0),(26,17,1,0),(46,8,9,1),(75,0,1,0)])
 dump=dict(flags=10,root=0,prototypes=[dict(parameters=3,frame_size=40,upvalues='',kgc=keys,knum=[],instructions=code)])
 enums={'NPC_UNIT_ID':{'ALPHA':a,'BETA':b,'ACCIDENTAL':accidental}}
 return dump,enums
def concrete(dump,enums,branch):
 npc=NPC();r={0:branch,2:npc};p=dump['prototypes'][0];pc=0
 while pc<len(p['instructions']):
  op,a,c,b=p['instructions'][pc];d=c|b<<8;pc+=1
  if op==12:r[a]=r[d]
  elif op==24:r[a]=d if d<32768 else d-65536
  elif op==26:r[a]=[None,False,True][d]
  elif op==62:r[a]=enums[p['kgc'][d]]
  elif op==65:r[a]=r[b][p['kgc'][c]]if isinstance(r[b],dict)else getattr(r[b],p['kgc'][c])
  elif op==46:
   args=[r[i]for i in range(a+2,a+c+1)];result=r[a](*args[1:])
   if b>=2:r[a]=result
  elif op==10:
   if r[a]is not[None,False,True][d]:pc+=1
  elif op==88:pc+=d-32768
  elif op==75:break
  else:raise AssertionError(op)
 return set(npc.created)
class Properties(unittest.TestCase):
 def test_generated_concrete_paths_equal_source_identity_union(self):
  rng=random.Random(20261104)
  for index in range(240):
   a,b=rng.sample(range(1000,20000),2);accidental=rng.choice([1,10,15,20,50,99]);dump,enums=fixture(a,b,accidental)
   expected=concrete(dump,enums,None)|concrete(dump,enums,object())
   analysis=Flow(dump,enums).spawn_results()
   self.assertEqual(len(analysis),1);self.assertEqual(set(analysis[0]['targets']),expected,(index,analysis));self.assertNotIn(accidental,analysis[0]['targets']);self.assertFalse(analysis[0]['unknown'])
 def test_native_boolean_and_numeric_table_keys_are_distinct(self):
  dump,enums=fixture(1001,1002,20);f=Flow(dump,enums)
  self.assertNotEqual(f.val(True),f.val(1));self.assertNotEqual(f.resolve(f.val(True)),f.resolve(f.val(1)))
 def test_source_enum_arithmetic_preserves_identity_only(self):
  dump,enums=fixture(1001,1002,20);f=Flow(dump,enums)
  identity=f.exp('lookup',f.exp('global','NPC_UNIT_ID'),f.val('ALPHA'));derived=f.resolve(f.exp('arithmetic',38,identity,f.val(1)));self.assertTrue(all(f.identity(x)for x in derived));self.assertEqual({f.number(x)for x in derived},{1002})
  self.assertFalse(any(f.identity(x)for x in f.resolve(f.exp('arithmetic',38,f.val(1001),f.val(1)))))
if __name__=='__main__':unittest.main()
