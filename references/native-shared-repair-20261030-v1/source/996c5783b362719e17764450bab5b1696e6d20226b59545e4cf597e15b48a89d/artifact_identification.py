"""Artifact equipment's two independent official random identification lines."""
from els_server.domain.artifact_progression import catalog

def supported(template):
 return template in catalog()['equipment']

def outcomes(template):
 c=catalog()
 if not supported(template):raise ValueError('Original Artifact equipment required')
 rows=c['equipment_identification'][c['equipment_probability_ids'][str(template)]]['rows']
 if sum(r['weight'] for r in rows)!=100000:raise ValueError('Incomplete Artifact identification probabilities')
 return rows

def validate(template,values):
 allowed={r['option'] for r in outcomes(template)}
 fixed=catalog()['mirror_fixed_options'].get(str(template))
 if not isinstance(values,(list,tuple)):raise ValueError('Invalid Artifact identification vector')
 if any(type(v) is not int for v in values):raise ValueError('Artifact option IDs must be integers')
 if not values:return []
 if fixed:
  # 1991810 filters the third TYPE=803/804/805/806 option from RANDOM(1)
  # into the real item's cached FIX vector. It is not a separate wire group.
  if len(values)!=3 or type(values[2]) is not int or values[2] not in {r['ID'] for r in fixed}:raise ValueError('Missing native Mirror fixed option')
  ordinary=values[:2]
  if ordinary==[0,0] or ordinary==(0,0):return list(values)
 else:ordinary=values
 if len(ordinary)!=2 or any(type(v) is not int or v not in allowed for v in ordinary):raise ValueError('Invalid Artifact identification lines')
 return list(values)

def unidentified_values(template,values):
 checked=validate(template,values)
 if str(template) in catalog()['mirror_fixed_options']:return not checked or len(checked)==3 and checked[:2]==[0,0]
 return not checked

def reset_values(template,values):
 checked=validate(template,values)
 if str(template) in catalog()['mirror_fixed_options']:
  if not checked:return []
  return [0,0,checked[2]]
 return []

def identify_values(template,values,randbelow):
 if str(template) in catalog()['mirror_fixed_options']:
  checked=validate(template,values)
  if not unidentified_values(template,checked):raise ValueError('Native unidentified Mirror fixed option required')
  from els_server.domain.local_artifact_rules import draw_fixed
  return draw(template,randbelow)+[checked[2] if checked else draw_fixed(template,randbelow)]
 return draw(template,randbelow)

def draw(template,randbelow):
 rows=outcomes(template)
 from els_server.domain.identification_ui import draw_slots
 return draw_slots(rows,2,randbelow,100000,
                   range_error='Artifact identification entropy bound')
