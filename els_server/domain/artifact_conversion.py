"""Mirror Artifact conversion: lock option families, reroll their values."""
from els_server.domain.artifact_progression import catalog
def validate(template,values):
 if template not in (168915,168916,168917,168918):raise ValueError('Mirror Artifact equipment required')
 if not isinstance(values,(list,tuple)) or len(values)!=3 or any(type(v) is not int or v and not 710000<=v<=710289 for v in values):raise ValueError('Invalid Artifact conversion vector')
 return list(values)
def draw(current,locked,randbelow):
 if not isinstance(locked,dict) or set(locked)-{0,1,2}:raise ValueError('Invalid Artifact conversion locks')
 if any(type(v) is not int or v!=current[i] or not v for i,v in locked.items()):raise ValueError('Stale or empty conversion lock')
 groups=catalog()['conversion']['groups']
 if len(groups)!=29 or sum(g['weight'] for g in groups)!=1000000:raise ValueError('Conversion probability identity')
 result=[]
 for index in range(3):
  if index in locked:group=(locked[index]-710000)//10
  else:
   ticket=randbelow(1000000)
   if type(ticket) is not int or not 0<=ticket<1000000:raise ValueError('Conversion group entropy bound')
   for group,row in enumerate(groups):
    if ticket<row['weight']:break
    ticket-=row['weight']
  level=randbelow(10)
  if type(level) is not int or not 0<=level<10:raise ValueError('Conversion value entropy bound')
  result.append(groups[group]['options'][level]['option'])
 return result
