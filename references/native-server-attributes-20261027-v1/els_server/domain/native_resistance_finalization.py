"""Original ordered resistance additions and upper cap, never a lower clamp."""
from els_server.domain.native_power_kernel import f32


def add(current,values):
    if any(type(v)is not tuple or len(v)!=6 for v in(current,values)):
        raise ValueError('Complete original six-float resistance inputs required')
    return tuple(f32(f32(a)+f32(b))for a,b in zip(current,values))


def service_after_311(previous,threshold):
    """B7C51F..B7C56C: allocation is retained on later lower/zero inputs."""
    if type(threshold)is not int or not 0<=threshold<=65535:
        raise ValueError('Original311 unsigned16 threshold required')
    if previous is not None:
        if type(previous)is not tuple or len(previous)!=6:
            raise ValueError('Explicit prior original service state required')
        return tuple(map(f32,previous))
    return (100.,)*6 if threshold>=2 else None


def finish(current,*,skill_values,service_values,resonance_value,post_values):
    """8653D8 onward; caller supplies ordered, already gated post contributions."""
    current=add(current,skill_values)
    if service_values is not None:current=add(current,service_values)
    current=add(current,(f32(resonance_value),)*6)
    if type(post_values)is not tuple:raise ValueError('Ordered post-option sources required')
    for value in post_values:current=add(current,value)
    return tuple(500. if v>500. else v for v in current)
