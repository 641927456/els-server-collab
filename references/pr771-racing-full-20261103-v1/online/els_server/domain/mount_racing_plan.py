"""Server-drawn native boosters; the client retains its race animation.

Base probabilities/ranges come from RidingPetRacingData. Each saved point
shifts two probability points from normal to high/super equally, and adds
ChangeSpeed_Max_Over to speed. Those two effects are local growth rules.
The server's 60 Hz finish clock is a local adjudication rule, not retail physics.
"""
import functools,json,secrets,struct
from els_server.paths import PROJECT_ROOT
from els_server.domain.mount_racing_rules import profile,policy


@functools.lru_cache(maxsize=1)
def physics():
    return json.loads((PROJECT_ROOT/'els_server/data/mount_racing_physics.json').read_bytes())


def f32(x):return struct.unpack('>f',struct.pack('>f',x))[0]


def step(curve,dt):
    """Original2B22FE0 float32 curve clock, including boundary behavior.

    After crossing a deadline the native code stores that deadline first,
    then subtracts deadline minus the stored clock (zero). The next stage
    consequently receives the complete frame dt. Preserve this witnessed
    behavior instead of substituting continuous-time integration.
    """
    dt=f32(dt);elapsed=curve[0];delta=0.
    for end,rate in curve[1]:
        if elapsed<end:
            if f32(elapsed+dt)<=end:
                delta=f32(delta+f32(rate*dt));elapsed=f32(elapsed+dt);break
            delta=f32(delta+f32(f32(end-elapsed)*rate));elapsed=end
    curve[0]=elapsed
    return delta


def draw(saved,lane,randbelow=secrets.randbelow):
    saved=profile(saved['experience'],saved['stats'])
    if type(lane)is not int or not 0<=lane<6:raise ValueError('Racing lane')
    def booster(category,attribute):
        templates=physics()['boosters'][category];roll=randbelow(100)
        if type(roll)is not int or not 0<=roll<100:raise ValueError('Racing random source')
        points=saved['stats'].get(attribute,0)
        weights=[t['Probability']+points*shift for t,shift in zip(templates,policy()['booster_probability_shift_per_point'])]
        for kind,(t,weight) in enumerate(zip(templates,weights)):
            if roll<weight:break
            roll-=weight
        fraction=randbelow(10001)
        if type(fraction)is not int or not 0<=fraction<=10000:raise ValueError('Racing speed draw')
        speed=t['ChangeSpeed_Min']+(t['ChangeSpeed_Max']-t['ChangeSpeed_Min'])*fraction/10000
        speed+=t['ChangeSpeed_Max_Over']*points
        return [kind,f32(speed)]
    start=booster('start',0);normal=[booster('normal',1)for _ in range(22)]
    obstacle=[booster('obstacle',2)for _ in physics()['obstacles']]
    spurt=booster('spurt',3);t=physics()['boosters']['spurt'][spurt[0]]
    fraction=randbelow(10001)
    if type(fraction)is not int or not 0<=fraction<=10000:raise ValueError('Racing spurt draw')
    remain=f32(t['StartRemainTime_Min']+(t['StartRemainTime_Max']-t['StartRemainTime_Min'])*fraction/10000)
    return dict(lane=lane,start=start,normal=normal,obstacle=obstacle,spurt=spurt,remain=remain)


def finish(plan):
    """Adjudicate the saved plan, never a player's rank or claimed time.

    Acceleration curves follow 2B30630/2B30A60/2B30EC0/2B314A0.
    TopYPos is vertical display displacement and does not advance the track.
    """
    p=physics();hz=policy()['race_adjudication_hz'];dt=f32(1/hz);curves=[];distance=elapsed=0.;speed=1.;maximum=1.
    normal=obstacle=0;inside=False;spurt=False;next_booster=p['race']['BoosterCooltime']
    def add(category,pair,enter=False):
        kind,change=pair;t={k:f32(v)if type(v)in(int,float)else v for k,v in p['boosters'][category][kind].items()}
        if category=='obstacle'and enter:
            stages=[(t['Obstacle_AccelerationTime'],f32(t['Obstacle_ChangeSpeed']/t['Obstacle_AccelerationTime']))]
        else:
            a=t['AccelerationTime'];initial=t['Obstacle_ChangeSpeed']if category=='obstacle'else 0.
            stages=[(a,f32(f32(change-initial)/a))]
            if category!='spurt':
                hold=t['HoldTime'];decel=t['DecelerationTime']
                end=f32(a+hold);stages.extend([(end,0.),(f32(end+decel),f32(-change/decel))])
        curves.append([0.,stages])
    add('start',plan['start'])
    # The track has four obstacles and a positive baseline speed. This limit
    # rejects a corrupt saved plan; it is not a client-report timeout award.
    for tick in range(hz*180):
        delta=0.
        for curve in curves:delta=f32(delta+step(curve,dt))
        speed=max(f32(.1),f32(speed+delta));maximum=max(maximum,speed)
        distance=f32(distance+f32(speed*dt));elapsed=f32(elapsed+dt)
        if distance>=p['race']['FinishLineTime']:
            return dict(time=f32(elapsed-(distance-p['race']['FinishLineTime'])/speed),max_speed=f32(maximum))
        if obstacle<len(p['obstacles']):
            t=p['obstacles'][obstacle]
            if not inside and distance>t['StartTime']:
                inside=True;add('obstacle',plan['obstacle'][obstacle],True)
            if inside and distance>t['BottomTime']:
                inside=False;add('obstacle',plan['obstacle'][obstacle]);obstacle+=1
        if elapsed>next_booster and normal<len(plan['normal']):
            add('normal',plan['normal'][normal]);normal+=1;next_booster+=p['race']['BoosterCooltime']
        if not spurt and p['race']['FinishLineTime']-distance<=plan['remain']:
            spurt=True;add('spurt',plan['spurt'])
    raise ValueError('Racing plan did not finish')


def standings(plans):
    rows=[dict(uid=uid,lane=p['lane'],**finish(p))for uid,p in plans.items()]
    rows.sort(key=lambda r:(r['time'],r['lane']))
    return [dict(r,rank=rank)for rank,r in enumerate(rows,1)]
