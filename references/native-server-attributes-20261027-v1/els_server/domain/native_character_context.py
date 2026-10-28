"""Native character-copy source boundary, distinct from later actor updates."""
from dataclasses import dataclass
import struct
from els_server.domain.native_rank_coefficient import rank_after_profile0


@dataclass(frozen=True)
class CharacterContext:
    rank:int
    stage:int
    grade:int
    first_count:int
    second_count:int
    world_buff_ids:tuple

    def pve(self):
        return {key:getattr(self,key)for key in('stage','grade','first_count','second_count')}


def after_character_copy(profile_wire,pve_wire,*,previous_rank):
    """Current writer's6A/3C5 sources -> original copy semantics.

    The installed writer emits the canonical empty profile map, so it preserves
    the previous rank. A future nonempty writer must qualify its complete value
    codec instead of treating it as empty. PvE input is the complete25-byte
    packed record; neighboring fields are intentionally not combat inputs.
    Unit2738 is unconditionally cleared at this boundary, including when its
    previous list was nonempty. No other update implicitly calls this function.
    """
    if type(profile_wire)is not bytes or profile_wire!=bytes(4):
        raise ValueError('Qualified current complete profile-map wire required')
    if type(pve_wire)is not bytes or len(pve_wire)!=25:
        raise ValueError('Complete original packed PvE source required')
    stage,_,_,grade,first,second,_=struct.unpack('>3ib3i',pve_wire)
    return CharacterContext(rank_after_profile0({},previous_rank=previous_rank),
        stage,grade,first,second,())
