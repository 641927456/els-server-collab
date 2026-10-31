"""Original887F00 over the current owned ERP source and a fresh record."""
import hashlib,json
from els_server.domain.native_power_kernel import f32
from els_server.domain.native_extension_inputs import contribution

FIELDS=frozenset((0x1ec,0x1e8,0x36c,0x410,0x118,0x370,0x374,0x4f0))
DEFINITION_SHA256='44fafbf5bd676453af0c5ad9d38b83bb853ae9a9a4a0d123f77dfbb0b0cb992a'


def definition_inputs(raw):
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest()!=DEFINITION_SHA256:
        raise ValueError('Qualified current resonance definition required')
    source=json.loads(raw)
    return {r['stat_id']:(r['per_point'],r['maximum'],int(r['dungeon_only']))for r in source['rows']}


def apply_resonance(fields, points, override, definitions, *, pvp, pvp_scale):
    if type(fields) is not dict or set(fields)!=FIELDS:
        raise ValueError('All original resonance scalar destinations required')
    if type(pvp) is not bool:raise ValueError('Explicit original phase mode required')
    out={k:f32(v)for k,v in fields.items()}
    pvp_scale=f32(pvp_scale)
    def get(stat):
        return contribution(points,override,definitions,stat,1-int(pvp),pvp_scale)
    damage={};cooldown={}
    #98B5D0 creates these maps empty immediately before887F00.
    for category,specific in((13,10),(6,6),(14,7),(15,8),(16,9)):
        current=f32(get(specific)*f32(.01))
        if category!=13:current=f32(f32(get(18)*f32(.01))+current)
        damage[category]=current
        cooldown[category]=f32(get(12)*f32(-.01))
    for stat,offset,subtract in((13,0x1ec,False),(14,0x1e8,False),
        (15,0x36c,False),(11,0x410,True),(19,0x118,False),
        (20,0x370,False),(21,0x374,True),(22,0x4f0,False)):
        value=f32(get(stat)*f32(.01))
        out[offset]=f32(out[offset]-value)if subtract else f32(value+out[offset])
    return out,damage,cooldown
