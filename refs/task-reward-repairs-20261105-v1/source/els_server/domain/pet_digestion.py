"""Current PetData nutritional hours and digestive reductions; native UI timers."""
from functools import lru_cache
import json
from els_server.domain.pet_progression import catalog
from els_server.paths import PROJECT_ROOT

# Current CN pet-growth guide:006-1583-002a2-308380.shtml. The older
# 72-hour introduction is superseded by this168-hour game-system guide.
MAX_DIGEST_SECONDS=168*3600

@lru_cache(maxsize=1)
def decreases():
    catalog() # Verify the existing pinned PetData source before using its calls.
    data=json.loads((PROJECT_ROOT/'analysis/pet-mount-20261015/resources/PetData.tables.json').read_bytes())
    return {r['arguments'][1]:r['arguments'][2]*3600 for r in data['__symbolic_calls__']if r['function']=='g_pPetManager.AddPetDecreaseDigestTimeItem'}

def nutrient(item):
    rules=catalog();t=item['template']
    if t in rules['restricted']:raise ValueError('Restricted pet nutrition item')
    row=rules['nutrients'].get(str(t))
    if row is not None:return row['points'],row['type']*3600
    from els_server.domain.normal_equipment import definitions
    if item['group']==1 and t in definitions():return 1,5*3600 # PetData.SetEquipItemNutrientInfo(1,5).
    raise ValueError('Original pet nutrient item required')
