"""Relevant projection/lifecycle checks and original x64 codec execution."""
import hashlib,json,math,os,struct,sys,unittest,uuid
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

OUT=Path(__file__).parent
ROOT=Path(os.environ.get('ELS_WORKSPACE','G:/els'))
SOURCE=Path(os.environ['ELS_STATS_CANDIDATE'])
for binding in json.loads((OUT.parent/'source-bindings.json').read_bytes())['source_files']:
    assert hashlib.sha256((SOURCE/binding['path']).read_bytes()).hexdigest()==binding['sha256'],binding['path']
sys.dont_write_bytecode=True
sys.path[:0]=[str(SOURCE),str(SOURCE/'tools'),str(ROOT/'tools')]
from els_server.protocol.protocol_codec import Event
from els_server.protocol.pvp_play_messages import hp_report
from els_server.domain.dungeon_clear import reward_clear_notice
from els_server.domain import dungeon_result_stats as result
from role_native_replay import Replay,IMAGE_SHA


def tree(r,p,values):
    head=struct.unpack('<Q',r.read(p,8))[0]
    nodes=[r.alloc(0x30)for _ in values]
    pairs=sorted(values.items())
    if not nodes:return
    r.write(head,struct.pack('<QQQ',nodes[0],nodes[0],nodes[-1]))
    r.write(p+8,struct.pack('<Q',len(nodes)))
    for i,(key,value)in enumerate(pairs):
        node=nodes[i]
        r.write(node,struct.pack('<QQQ',head,head if i==0 else nodes[i-1],
                                nodes[i+1]if i+1<len(nodes)else head))
        r.write(node+32,struct.pack('<Qf',key,value))


def native_report(r,uid,damage,recovery=(100,80,30,20),received=44,skills=0):
    dto=r.alloc(0x180);r.call(0xc79fb0,dto)
    r.write(dto,struct.pack('<f',1234))
    r.write(dto+0x28,struct.pack('<f',500))
    r.write(dto+0x2c,struct.pack('<i',received))
    # 1AB6EB0 supplies actor v6C0's boolean; constructor sentinel is 0xFF.
    r.write(dto+0x101,b'\0')
    # Include a second observer's UID in every map. Summing peers would
    # incorrectly double these cumulative counters.
    for n,value in enumerate(damage):tree(r,dto+0x30+n*16,{uid:value,9999:777})
    r.write(dto+0xb0,struct.pack('<4f',*recovery))
    tree(r,dto+0xc0,{9999:2.5}) # original CD producer excludes its local UID
    for n in range(4):
        if not skills:break
        p=dto+0x11a+16*n;head=struct.unpack('<Q',r.read(p,8))[0]
        outer=r.alloc(0x40);inner=r.alloc(0x30)
        r.write(head,struct.pack('<QQQ',outer,outer,outer));r.write(p+8,struct.pack('<Q',1))
        r.write(outer,struct.pack('<QQQ',head,head,head));r.write(outer+32,struct.pack('<Q',uid))
        r.write(outer+40,struct.pack('<QQ',inner,skills))
        nodes=[r.alloc(0x30)for _ in range(skills)]
        r.write(inner,struct.pack('<QQQ',nodes[0],nodes[0],nodes[-1]));r.write(inner+25,b'\1')
        for i,node in enumerate(nodes):
            r.write(node,struct.pack('<QQQ',inner,inner if i==0 else nodes[i-1],
                                    nodes[i+1]if i+1<skills else inner))
            r.write(node+28,struct.pack('<if',i+1,100.5+i))
    storage=r.alloc(65536);buf=r.alloc(48)
    r.write(buf+8,struct.pack('<QQQ',storage,storage,storage+65536))
    stream=r.alloc(40);r.call(0x3b6d140,stream);r.call(0x3b6d1c0,stream,buf,0)
    assert r.call(0xda2f50,stream,dto)&255==1
    start,end,cap=struct.unpack('<QQQ',r.read(buf+8,24))
    assert start<=end<=cap
    return r.read(start,end-start)


def session(uid,epoch=None):
    s=N(account=N(uid=uid),reward_run_id=epoch or str(uuid.uuid4()),gate_stage=2,
        dungeon_run=None,phase='dungeon_active',dungeon_substage_synced=True,
        clear_notified=False,enter_dungeon=True,dungeon_participants=frozenset((uid,)))
    return s


def recipient_report(raw,values):
    return raw+b'PVE1'+struct.pack('>I',len(values))+b''.join(
        struct.pack('>Qf',uid,value)for uid,value in sorted(values.items()))


def decoded(r,raw):
    data=r.alloc(len(raw));r.write(data,raw);buf=r.alloc(48)
    r.write(buf+8,struct.pack('<QQQ',data,data+len(raw),data+len(raw)))
    stream=r.alloc(40);dto=r.alloc(0x140)
    r.call(0xc7a810,dto);r.call(0x3b6d140,stream);r.call(0x3b6d1c0,stream,buf,0)
    assert r.call(0xda64c0,stream,dto)&255==1
    assert struct.unpack('<I',r.read(buf+32,4))[0]==len(raw)
    begin,end=struct.unpack('<QQ',r.read(dto+0x1b,16))
    assert (end-begin)%0x1c9==0
    rows=[]
    for p in range(begin,end,0x1c9):
        rows.append(dict(uid=struct.unpack('<Q',r.read(p,8))[0],
            ed=struct.unpack('<Q',r.read(p+0x31,8))[0],
            experience=struct.unpack('<Q',r.read(p+0x41,8))[0],
            received=struct.unpack('<i',r.read(p+0xfa,4))[0],
            rank=r.read(p+0x17c,1)[0],mvp=bool(r.read(p+0x17d,1)[0]),
            values={hex(o):struct.unpack('<f',r.read(p+o,4))[0]
                for o in (0xfe,0x140,0x144,0x148,0x14c,0x150,0x154,0x158,0x15c,0x160,0x164,0x168,0x16c)}))
    return rows


class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native=Replay()
        cls.wire1=native_report(cls.native,1001,(1000,800,200,700,600,100,50,40))
        cls.wire2=native_report(cls.native,1002,(3000,2000,1000,2900,1950,950,90,80),(500,300,100,50),123)

    def capture(self,s,wire,seq=1):
        event=Event(0x202,kind=0x9e,payload=wire)
        with patch('els_server.domain.dungeon_equipment_loot_flow.current_lease',return_value=True):
            return result.report(s,event,seq)

    def test_native_writer_crosschecks_statistics(self):
        p=hp_report(self.wire1,statistics=True)
        self.assertEqual(p.hp,1234)
        self.assertEqual([m[1001]for m in p.statistics['damage']],
                         [1000,800,200,700,600,100,50,40])
        self.assertEqual(p.statistics['received'],44)
        self.assertEqual(p.statistics['recovery'],(100,80,30,20))
        self.assertEqual(p.statistics['cooldown'][9999],2.5)
        self.assertIsNone(hp_report(self.wire1).statistics)

    def test_bad_reports_do_not_replace_snapshot(self):
        s=session(1001);self.assertEqual(self.capture(s,self.wire1)[0].payload,bytes(4))
        saved=s.dungeon_result_report
        for wire in (self.wire1[:-1],self.wire1+b'\0',b'\0'*181,
                     struct.pack('>f',math.nan)+self.wire1[4:]):
            self.assertNotEqual(self.capture(s,wire,2)[0].payload,bytes(4))
            self.assertIs(s.dungeon_result_report,saved)
        self.assertNotEqual(self.capture(s,self.wire2,1)[0].payload,bytes(4))
        self.assertIs(s.dungeon_result_report,saved)
        self.assertEqual(self.capture(s,self.wire1,1)[0].payload,bytes(4))
        s.clear_notified=True
        self.assertEqual(self.capture(s,self.wire1,3)[0].payload,bytes(4))
        self.assertEqual(self.capture(s,self.wire2,3)[0].payload,bytes(4))
        self.assertNotEqual(self.capture(s,self.wire2,1)[0].payload,bytes(4))
        self.assertIs(s.dungeon_result_report,saved)

    def test_full_run_skill_report_exceeds_pvp_limit(self):
        wire=native_report(self.native,1001,(1000,800,200,700,600,100,50,40),skills=300)
        self.assertGreater(len(wire),8192)
        parsed=hp_report(wire,statistics=True)
        self.assertEqual(parsed.statistics['skills'][3][1001][300],399.5)
        with self.assertRaises(ValueError):hp_report(wire)

    def test_solo_native_result_preserves_rewards(self):
        s=session(1001);self.capture(s,self.wire1);s.clear_notified=True
        original=reward_clear_notice(120,50,1001,elapsed_seconds=83,best_seconds=61,map_id=30000)
        event=result.project(s,original)
        rows=decoded(self.native,event.payload)
        self.assertEqual((rows[0]['uid'],rows[0]['ed'],rows[0]['experience']),(1001,120,50))
        self.assertEqual(rows[0]['values']['0xfe'],1000)
        self.assertEqual(rows[0]['values']['0x164'],700)
        self.assertEqual(rows[0]['values']['0x148'],50)
        self.assertEqual(rows[0]['received'],44)
        self.assertTrue(rows[0]['mvp']);self.assertEqual(rows[0]['rank'],0)
        self.assertEqual(struct.unpack_from('>i',event.payload,460)[0],61)
        self.assertEqual(result.project(s,original),event)

    def test_solo_mvp_does_not_award_failure_or_change_amounts(self):
        from els_server.domain.dungeon_clear import failed_clear_notice
        s=session(1001);s.clear_notified=True
        failed=failed_clear_notice(1001,map_id=30000)
        row=decoded(self.native,result.project(s,failed).payload)[0]
        self.assertFalse(row['mvp']);self.assertEqual((row['ed'],row['experience']),(0,0))
        self.assertEqual(row['rank'],0)

    def test_shared_roster_never_sums_observers(self):
        a,b=session(1001),session(1002)
        self.capture(a,self.wire1);self.capture(b,self.wire2)
        room=N(members=(a,b),seed=str(uuid.uuid4()))
        app=N(world=N(dungeons=N(room=lambda _:room)))
        for s in (a,b):
            s.application=app;s.dungeon_participants=frozenset((1001,1002));s.clear_notified=True
        first=reward_clear_notice(120,50,1001,map_id=30000)
        second=reward_clear_notice(240,80,1002,map_id=30000)
        a.reward_receipt=dict(response=first.payload);b.reward_receipt=dict(response=second.payload)
        ea=result.project(a,first);eb=result.project(b,second)
        ra=decoded(self.native,ea.payload);rb=decoded(self.native,eb.payload)
        self.assertEqual(ra,rb)
        self.assertEqual([v['uid']for v in ra],[1001,1002])
        self.assertEqual([v['values']['0xfe']for v in ra],[1000,3000])
        self.assertEqual([v['ed']for v in ra],[120,240])
        self.assertTrue(all(not v['mvp']for v in ra))
        b.reward_run_id=str(uuid.uuid4())
        b.account=N(uid=2002) # same connection selects a different character
        self.assertEqual(result.project(a,first),ea) # already sealed room result

    def test_new_stage_and_new_run_drop_old_statistics(self):
        s=session(1001);self.capture(s,self.wire1)
        s.gate_stage=1;self.assertIsNone(result.current_statistics(s))
        self.capture(s,self.wire2,2);self.assertIsNotNone(result.current_statistics(s))
        s.reward_run_id=str(uuid.uuid4());self.assertIsNone(result.current_statistics(s))
        s.phase='town_ready';self.assertNotEqual(self.capture(s,self.wire1,3)[0].payload,bytes(4))

    def test_recipient_cooldown_never_sums_observer_copies(self):
        a,b=session(1001),session(1002)
        self.capture(a,recipient_report(self.wire1,{1002:3.5}))
        self.capture(b,recipient_report(self.wire2,{1001:7.5}))
        room=N(members=(a,b),seed=str(uuid.uuid4()))
        app=N(world=N(dungeons=N(room=lambda _:room)))
        events=[reward_clear_notice(120,50,s.account.uid,map_id=30000)for s in(a,b)]
        for s,event in zip((a,b),events):
            s.application=app;s.dungeon_participants=frozenset((1001,1002));s.clear_notified=True
            s.reward_receipt=dict(response=event.payload)
        first=result.project(a,events[0]);rows=decoded(self.native,first.payload)
        self.assertEqual([r['values']['0x160']for r in rows],[7.5,3.5])
        self.assertEqual([r['values']['0xfe']for r in rows],[1000,3000])
        self.assertEqual(result.project(b,events[1]).payload[27:825],first.payload[27:825])
        # A provider's already known contribution is displayable even if its
        # own report is missing; that report is not the recipient ledger.
        delattr(a,'dungeon_result_report');delattr(room,'dungeon_result_rows')
        rows=decoded(self.native,result.project(a,events[0]).payload)
        self.assertEqual(rows[0]['values']['0x160'],7.5)

    def test_pve_extension_bounds_and_pvp_contract(self):
        valid=recipient_report(self.wire1,{1002:3.5});s=session(1001)
        self.assertEqual(self.capture(s,valid)[0].payload,bytes(4));saved=s.dungeon_result_report
        for bad in(valid[:-1],valid+b'\0',recipient_report(self.wire1,{1001:1}),
                   recipient_report(self.wire1,{0:1}),recipient_report(self.wire1,{1002:math.nan}),
                   self.wire1+b'PVE1'+struct.pack('>I',2)+struct.pack('>QfQf',1002,1,1002,2)):
            self.assertNotEqual(self.capture(s,bad,2)[0].payload,bytes(4))
            self.assertIs(s.dungeon_result_report,saved)
        with self.assertRaises(ValueError):hp_report(valid)
        pvp=self.wire1+b'PVP1'+struct.pack('>f',2000)
        self.assertEqual(hp_report(pvp).maximum_hp,2000)
        self.assertNotEqual(self.capture(s,pvp,2)[0].payload,bytes(4))

    def test_cd_aggregate_rejected_before_snapshot_or_clear(self):
        a,b,c=(session(u)for u in(1001,1002,1003));room=N(members=(a,b,c),seed=str(uuid.uuid4()))
        app=N(world=N(dungeons=N(room=lambda _:room)))
        for s in(a,b,c):s.application=app;s.dungeon_participants=frozenset((1001,1002,1003))
        maximum=struct.unpack('>f',bytes.fromhex('7f7fffff'))[0]
        self.assertEqual(self.capture(a,recipient_report(self.wire1,{1003:maximum}))[0].payload,bytes(4))
        self.assertNotEqual(self.capture(b,recipient_report(self.wire2,{1003:maximum}))[0].payload,bytes(4))
        self.assertFalse(hasattr(b,'dungeon_result_report'))
        # Totals that round to a finite native f32 remain valid.
        self.assertEqual(self.capture(b,recipient_report(self.wire2,{1003:1}))[0].payload,bytes(4))
        totals=result.cooldown_payloads(room.members,a.dungeon_participants)
        self.assertEqual(struct.unpack('>f',totals[1003])[0],maximum)


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    outcome=unittest.TextTestRunner(verbosity=2).run(suite)
    (OUT/'statistics-verification.json').write_text(json.dumps(dict(
        passed=outcome.wasSuccessful(),tests=outcome.testsRun,failures=len(outcome.failures),
        errors=len(outcome.errors),image_sha256=IMAGE_SHA,
        original_writer='0xda2f50',original_result_reader='0xda64c0',
        natural_GUI=False,natural_battle=False,production_mutation=False),indent=2)+'\n')
    raise SystemExit(0 if outcome.wasSuccessful()else 1)
