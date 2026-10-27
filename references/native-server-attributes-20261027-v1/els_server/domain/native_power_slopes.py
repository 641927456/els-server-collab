"""Offline scalar subset of original988320; no full actor builder or writes."""
from els_server.domain.native_power_kernel import f32

# Each row: three transition thresholds after the linear segment, three slopes,
# two intermediate intercepts, final cap. All operations below remain float32.
RULES={
    0x987de0:(40.,75.,105.,140.,.8,.6,.4,68.,86.,100.),
    0x987e90:(40.,80.,120.,160.,.75,.5,.25,70.,90.,100.),
    0x987f50:(30.,55.,85.,110.,.35,.25,.15,38.75,46.25,50.),
    0x988000:(40.,80.,125.,165.,.75,.5,.25,70.,92.5,102.5),
    0x9880d0:(20.,35.,55.,70.,.3,.2,.1,24.5,28.5,30.),
    0x988180:(20.,45.,70.,95.,.5,.35,.15,32.5,41.25,45.),
}
SOURCE_TO_DERIVED={0xf4:(0x7b8,0x987de0),0x198:(0x7bc,0x987e90),0x180:(0x7c8,0x987f50),0x188:(0x7d0,0x987f50),0x114:(0x7d8,0x988000),0x18:(0x7e4,0x9880d0),0x110:(0x7e8,0x988180)}

def normalize(target,value):
    if type(target) is not int or target not in RULES:raise ValueError('Unverified original normalization target')
    v=f32(value);lo,t1,t2,t3,a,b,c,y1,y2,cap=RULES[target]
    if v<lo:out=v
    elif v<t1:out=f32(f32(f32(v-lo)*f32(a))+lo)
    elif v<t2:out=f32(f32(f32(v-t1)*f32(b))+y1)
    elif v<t3:out=f32(f32(f32(v-t2)*f32(c))+y2)
    else:out=cap
    return f32(out*f32(.01))

def scalar_updates(raw):
    """Return only seven explicitly sourced fields; refuses missing raw inputs."""
    if set(raw)!=set(SOURCE_TO_DERIVED):raise ValueError('Incomplete scalar-normalization input')
    return {dest:normalize(target,raw[src]) for src,(dest,target) in SOURCE_TO_DERIVED.items()}
