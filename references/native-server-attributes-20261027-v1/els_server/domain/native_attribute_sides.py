"""Assemble original106's two side caches from one current source generation."""
from dataclasses import dataclass
from els_server.domain.native_power_kernel import f32


@dataclass(frozen=True)
class CalculatedSide:
    owner_uid:int
    unit_type:int
    unit_class:int
    generation:int
    source_sha256:str
    selector:int
    pvp_mode:int
    seven:tuple
    power:tuple
    valid_before:int|None


def notification_sides(first,second,*,owner_uid,unit_type,unit_class,generation,
                       source_sha256,pvp_mode,at):
    if (type(owner_uid)is not int or not 0<owner_uid<2**64
        or type(unit_type)is not int or not 1<=unit_type<=15
        or type(unit_class)is not int or not 0<unit_class<2**31
        or type(generation)is not int or not 0<=generation<2**63
        or type(pvp_mode)is not int or pvp_mode not in(0,1)
        or type(at)is not int or not 0<at<2**40):
        raise ValueError('Complete current native side identity required')
    if (type(source_sha256)is not str or len(source_sha256)!=64
        or any(v not in'0123456789abcdef'for v in source_sha256)):
        raise ValueError('Current owned source digest required')
    expected=(owner_uid,unit_type,unit_class,generation,source_sha256,pvp_mode)
    def read(row,selector):
        if type(row)is not CalculatedSide:
            raise ValueError('Complete calculated native side required')
        if (any(type(value)is not int for value in(row.owner_uid,row.unit_type,row.unit_class,row.generation,row.pvp_mode))
            or type(row.source_sha256)is not str):
            raise ValueError('Exact native side identity types required')
        actual=(row.owner_uid,row.unit_type,row.unit_class,row.generation,row.source_sha256,row.pvp_mode)
        if actual!=expected or type(row.selector)is not int or row.selector!=selector:
            raise ValueError('Native side generation, mode or selector changed')
        if type(row.seven)is not tuple or len(row.seven)!=7 or type(row.power)is not tuple or len(row.power)!=2:
            raise ValueError('Complete native seven and both power results required')
        seven=tuple(map(f32,row.seven));power=tuple(map(f32,row.power))
        if seven[0]<=0 or min(seven)<0 or min(power)<0 or power[0]>4294967040:
            raise ValueError('Native calculated side outside admitted finite range')
        if row.valid_before is not None:
            if type(row.valid_before)is not int or not 0<row.valid_before<2**40 or at>=row.valid_before:
                raise ValueError('Native side source expired; capture again')
        return seven,power
    first_seven,first_power=read(first,0)
    if unit_type==10:
        second_seven,second_power=read(second,1)
        other=second_power[0]
    else:
        if second is not None:raise ValueError('Single-role notification must reuse its first result')
        second_seven=first_seven;other=0.
    # OriginalC2C87F..C2C888 uses MAXSS, which selects operand2 on equality.
    # Keep its signed-zero result; all inputs were already checked finite.
    power=first_power[0]if first_power[0]>other else other
    return dict(first_seven=first_seven,second_seven=second_seven,power=power)
