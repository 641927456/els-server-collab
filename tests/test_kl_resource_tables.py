"""Read captured native bytecode tables; reject damaged or executable paths."""
import copy,json,sys
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE/'tools'))
from read_kl_bytecode import read,initializer
ROOT=BASE/'analysis/client-6c6b5180/resource-scripts'
data=(ROOT/'Dungeon_Ruben_El_Tree_Normal.lua').read_bytes()
parsed=read(data);tables=initializer(parsed)['STAGE_LIST']
gate=tables['STAGE0']['SUB_STAGE0']['NPC_GROUP'][7]
assert gate['NPC_ID']['global']=='NPC_UNIT_ID.NUI_RUBEN_EL_TREE_GATE' and gate['START_POS'][1]==12
assert tables['STAGE0']['SUB_STAGE0']['CLEAR_COND0']['NPC_ID'][1]['global']==gate['NPC_ID']['global']
assert tables['STAGE2']['SUB_STAGE0']['NPC_GROUP'][1]['NPC_ID']['global']=='NPC_UNIT_ID.NUI_BENDERS_NORMAL'
positions=initializer(read((ROOT/'Ruben_El_Tree_Stage1_LineMap.lua').read_bytes()))['__symbolic_calls__']
p=next(x for x in positions if x['function']=='g_pLineMap.AddStartPos' and x['arguments'][1]==12)
assert p['arguments'][2]['symbolic_call']['arguments']==[2803,40,1060]
for damaged in [data[:-1],data+b'\0',data.replace(b'\x1bKL\x82',b'\x1bLJ\x02',1),data[:4]+b'\0'+data[5:]]:
 try:read(damaged)
 except ValueError:pass
 else:raise AssertionError('Malformed dump accepted')
d=copy.deepcopy(parsed);d['prototypes'][d['root']]['instructions'][0]=(0xff,0,0,0)
try:initializer(d)
except ValueError:pass
else:raise AssertionError('Unrecognized initializer operation accepted')
print('PASS: recovered gate clear condition, native exit position, Boss condition, malformed bytecode and unknown operation rejection; static symbolic interpretation only.')
