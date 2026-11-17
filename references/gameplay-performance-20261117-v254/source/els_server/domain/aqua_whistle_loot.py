"""Aqua Whistle local drop policy, not a claimed official probability table.

The original CREATED_NPC_DROP_TIMES caps admitted Duver spawns at fourteen.
Local allocation: five stones per admitted Duver, fifteen from the dam.
The 85-stone full-run budget and grade mix approximate a published 900-run
sample. Four types have equal local weight. See aqua-whistle policy evidence.
"""
GRAPH='67d64a407a69ee19bc55708af2beaf35b947d029487c8501d821a6df253246c0'
LIMIT=14
GRADE_WEIGHTS=(8960,930,100,10)

def encounter(run):
 return run is not None and run.identity==35700 and run.graph['source_sha256']==GRAPH

def admit(run,entries):
 keys=getattr(run,'aqua_drop_keys',())
 if encounter(run) and (run.stage,run.part)==(1,1):
  for npc in entries:
   if npc['template']==12266 and npc['active'] and not npc.get('ally') and npc.get('team',1)!=0 and len(keys)<LIMIT:
    keys=(*keys,(run.visits,npc['key']))
 return keys

def duver(run,npc):
 if not encounter(run) or (run.stage,run.part)!=(1,1):return 0
 if npc['template']!=12266 or not npc.get('dynamic') or not npc.get('active') or npc.get('ally') or npc.get('team',1)==0:return 0
 keys=getattr(run,'aqua_drop_keys',())
 key=(run.visits,npc['key'])
 if key not in keys:return 0
 if not any(n is npc for n in run.current['npcs']):return 0
 return keys.index(key)+1

def rewards(source,randbelow):
 if source.c['dungeon']!=35700:return []
 ordinal=source.origin.get('aqua_duver_ordinal')
 actor=tuple(source.c.get(k)for k in('stage','part'))+(source.origin['source_template'],source.origin['source_index'])
 count=5 if ordinal else 15 if actor==(2,0,12262,5) else 0
 from els_server.domain.dungeon_equipment_loot_rules import integer_draw
 result=[]
 for _ in range(count):
  draw=integer_draw(10000,randbelow);grade=0
  for grade,weight in enumerate(GRADE_WEIGHTS):
   if draw<weight:break
   draw-=weight
  result.append((136210+4*integer_draw(4,randbelow)+grade,1))
 return result
