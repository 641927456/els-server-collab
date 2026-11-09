"""Native pet nutrient points / digestion hours and digestive-time reductions."""
import functools,json
from els_server.paths import PROJECT_ROOT

# Native digestion ceiling. The current CN pet-growth guide supersedes the
# older 72-hour note with a 168-hour cap, and the client enforces it locally:
# once the remaining digestion time reaches it, the nutrient window refuses to
# register further items ("已达到最大消化时间或达到最大成长值"). The server must
# therefore never store a deadline beyond now + 168h, or every later feed is
# blocked before it even reaches 8AD.
MAX_DIGEST_SECONDS=168*60*60
SOURCE=PROJECT_ROOT/'analysis/pet-mount-20261015/resources/PetData.tables.json'

@functools.lru_cache(maxsize=1)
def tables():
    data=json.loads(SOURCE.read_text(encoding='utf8'))
    nutrients={};decrease={}
    for call in data['__symbolic_calls__']:
        name=call['function'];args=call['arguments']
        if name=='g_pPetManager.AddPetNutrientPointItem':
            template,points,hours=args[1],args[2],args[3]
            if any(type(v)is not int for v in (template,points,hours)) or not 0<template<2**31 or not 1<=points<=32767 or not 0<hours<=24:raise ValueError('Native pet nutrient entry')
            if template in nutrients:raise ValueError('Duplicate native pet nutrient item')
            nutrients[template]=(points,hours)
        elif name=='g_pPetManager.AddPetDecreaseDigestTimeItem':
            template,hours=args[1],args[2]
            if any(type(v)is not int for v in (template,hours)) or not 0<template<2**31 or not 0<hours<=24:raise ValueError('Native pet digestive entry')
            if template in decrease:raise ValueError('Duplicate native pet digestive item')
            decrease[template]=hours
    if not nutrients or not decrease:raise ValueError('Native pet digestion tables')
    return nutrients,decrease

def nutrient(item):
    """(points, digest seconds) for an owned nutrient stack or a bare template id.

    The native table stores whole hours; the stored deadline is an epoch second,
    so both reviewed consumers (8AD stacking and 8B9 reduction) work in seconds.
    """
    template=item if type(item)is int else item['template']
    try:points,hours=tables()[0][template]
    except KeyError:raise ValueError('Not a native pet nutrient item') from None
    return points,hours*3600

def decreases():return {template:hours*3600 for template,hours in tables()[1].items()}
