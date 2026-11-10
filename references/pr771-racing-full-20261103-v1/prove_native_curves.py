"""Native booster builders/integrator with no scene actors or rendering."""
from pathlib import Path
import hashlib,json,math,struct,sys
ROOT=Path('G:/els');W=Path(__file__).resolve().parent;R=ROOT/'analysis/pr771-firstbatch-20261103-v1/runtime'
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'tools/pylibs')]
from role_native_replay import Replay,IMAGE_SHA
from unicorn.x86_const import UC_X86_REG_XMM2
sys.path.insert(0,str(R))
from els_server.domain.mount_racing_plan import physics,f32,step


def tree(r,size):
    head=r.alloc(size);r.write(head,struct.pack('<QQQH',head,head,head,0x101));return head


def nodes(r,container):
    head,count=struct.unpack('<QQ',r.read(container,16));found=[]
    def walk(node):
        if node==head:return
        walk(int.from_bytes(r.read(node,8),'little'));found.append(node);walk(int.from_bytes(r.read(node+16,8),'little'))
    walk(int.from_bytes(r.read(head+8,8),'little'));assert len(found)==count;return found


def templates(r,game,offset,rows):
    head=tree(r,0x90);ptr=[r.alloc(0x90)for _ in rows]
    r.write(head,struct.pack('<QQQ',ptr[0],ptr[1],ptr[2]));r.write(game+offset,struct.pack('<QQ',head,3))
    for kind,(node,t)in enumerate(zip(ptr,rows)):
        r.write(node,struct.pack('<QQQH',ptr[0]if kind==1 else head,head if kind==1 else ptr[1],ptr[2]if kind==1 else head,1))
        r.write(node+0x20,struct.pack('<i',kind))
        r.write(node+0x30,struct.pack('<4f',t['ChangeSpeed_Min'],t['ChangeSpeed_Max'],t['ChangeSpeed_Max_Over'],t['AccelerationTime']))
        r.write(node+0x40,struct.pack('<ff',t.get('HoldTime',0.),t.get('DecelerationTime',0.)))
        r.write(node+0x68,struct.pack('<ffB',t.get('Obstacle_ChangeSpeed',0.),t.get('Obstacle_AccelerationTime',0.),bool(t.get('Obstacle_CanJump',False))))


r=Replay();vt=r.alloc(0x480);getter=r.alloc(8);r.write(getter,b'\x48\x8b\x41\x08\xc3')
zero=r.alloc(8);r.write(zero,b'\x31\xc0\xc3');r.write(vt+0x158,struct.pack('<Q',getter));r.write(vt+0x460,struct.pack('<Q',zero))
actor=r.alloc(16);r.write(actor,struct.pack('<QQ',vt,1));out=[]
for category,enter in(('start',False),('normal',False),('obstacle',True),('obstacle',False),('spurt',False)):
    game=r.alloc(0x1800);r.write(game+0x4d8,struct.pack('<Q',r.alloc(8)))
    for offset,key in((0x1440,'start'),(0x1450,'normal'),(0x1460,'obstacle'),(0x1470,'spurt')):templates(r,game,offset,physics()['boosters'][key])
    r.write(game+0x1480,struct.pack('<QQ',tree(r,0x40),0))
    runtime=r.alloc(0xb0);r.write(runtime,struct.pack('<Q',1));r.write(game+0x1738,struct.pack('<QQQ',runtime,runtime+0xb0,runtime+0xb0))
    template=physics()['boosters'][category][1];speed=f32((template['ChangeSpeed_Min']+template['ChangeSpeed_Max'])/2)
    r.write(runtime+0x68,struct.pack('<if',1,speed));r.write(runtime+0xa0,struct.pack('<iff',1,speed,32.))
    for offset in(0x70,0x88):
        pair=r.alloc(8);r.write(pair,struct.pack('<if',1,speed));r.write(runtime+offset,struct.pack('<QQQ',pair,pair+8,pair+8))
    target={'start':0x2b30630,'normal':0x2b30a60,'obstacle':0x2b30ec0,'spurt':0x2b314a0}[category]
    r.uc.reg_write(UC_X86_REG_XMM2,int.from_bytes(struct.pack('<f',31.),'little'))
    r.call(target,game,actor,int(enter),r.alloc(8))
    row,=nodes(r,game+0x1480);curves,end=struct.unpack('<QQ',r.read(row+0x28,16));assert end-curves==0x20
    stages=[struct.unpack('<ff',r.read(n+0x1c,8))for n in nodes(r,curves)]
    # Directly witness the client's integration across every stage boundary.
    checked=[]
    for dt in(.001,1/60,.16,.5,1.,5.,10.):
        elapsed=struct.unpack('<f',r.read(curves+0x10,4))[0]
        model=[elapsed,stages];expected=step(model,dt)
        r.uc.reg_write(UC_X86_REG_XMM2,int.from_bytes(struct.pack('<f',dt),'little'));r.call(0x2b22fe0,game,0,0)
        actual=struct.unpack('<f',r.read(curves+0x14,4))[0]
        checked.append(dict(dt=dt,expected=expected,actual=actual))
        native_elapsed=struct.unpack('<f',r.read(curves+0x10,4))[0]
        assert actual==expected and native_elapsed==model[0],(category,enter,checked[-1],stages)
    out.append(dict(category=category,enter=enter,stages=stages,checked=checked))
result=dict(ok=True,image_sha256=IMAGE_SHA,original_builders=True,original_integrator='2B22FE0',
            actor_UID_getter_is_ABI_test_double=True,scene_actor_vector_empty=True,rendering_executed=False,natural_GUI=False,cases=out,
            test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            sources={p:hashlib.sha256((R/p).read_bytes()).hexdigest()for p in('els_server/domain/mount_racing_plan.py','els_server/data/mount_racing_physics.json','els_server/data/mount_racing_local.json')})
(W/'native-racing-curves.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps(result))
