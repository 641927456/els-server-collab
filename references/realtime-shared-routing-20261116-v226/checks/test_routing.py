"""Compare batch publication with original per-sender/per-peer routing in RAM."""
import importlib.util,json,sys,time,unittest,uuid
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from contextlib import nullcontext
ROOT=Path(__file__).resolve().parents[1]
import argparse
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--runtime',type=Path,required=True)
options,rest=parser.parse_known_args()
sys.argv[1:]=rest
SRC=options.runtime.resolve(strict=True)
sys.path[:0]=[str(SRC),str(SRC/'vendor')]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
old=load('baseline_dungeons',SRC/'els_server/domain/friends_dungeon.py')
new=load('candidate_dungeons',ROOT/'source/els_server/domain/friends_dungeon.py')
class Actor:
    pass
class Registry:
    def __init__(self,n):self.ids=set(range(1,n+1));self.calls=0
    def enabled(self,a):self.calls+=1;return a in self.ids
    def enabled_snapshot(self):return nullcontext()
def fixture(n=4):
    absent=NS(room=lambda s:None,manifest=lambda *a:None,relay_target=lambda *a:None)
    w=NS(field_bosses=absent,weddings=absent,racing=absent,pet_battles=absent,pvp=absent,party_of={},parties={})
    app=NS(world=w,playing={},accounts={},registry=Registry(n));d=new.FriendsDungeons(w);w.dungeons=d
    members=[];party={'id':10,'members':members};w.parties[10]=party
    for a in range(1,n+1):
        s=Actor();s.application=app;s.account=NS(uid=1000+a,account_id=a,store=NS(uid=1000+a))
        root=NS(character_accounts={1000+a:s.account});s.account.root=root;app.accounts[a]=root
        s.identity={'id':a};s.role='game';s.phase='dungeon_active';s.coop_error=False;s.released=False;s.clear_notified=False
        s.photo_zone=None;members.append(s);app.playing[a]=s;w.party_of[s]=party
    room=new.Room(party,tuple(members),members[0],1,str(uuid.uuid4()));room.phase='active';party['run']=room
    d.rooms={s:room for s in members};return app,d,room
def original(app,d,r):
    result={}
    for a in app.playing:
        if not app.registry.enabled(a):continue
        m=old.FriendsDungeons.manifest(d,app,a)
        if m is None:continue
        routes={}
        for p in m['peers']:
            t=old.FriendsDungeons.relay_target(d,app,a,m['epoch'],p['uid'])
            if t is not None:routes[a,m['epoch'],p['uid']]=t
        result[a]=(m,routes)
    return result
class RoutingTests(unittest.TestCase):
    def compare(self,mutate=lambda *a:None,n=4):
        app,d,r=fixture(n);mutate(app,d,r)
        with patch('els_server.domain.photo_zone_flow.manifest',return_value=None),patch('els_server.domain.photo_zone_flow.relay_target',return_value=None):
            before=original(app,d,r);after=d.routing(app,r)
        self.assertEqual(before,after);return app,d,r,after
    def test_all_pairs_and_stable_native_ports(self):
        for n in (1,2,4,6,8):
            with self.subTest(n=n):
                _,_,r,value=self.compare(n=n)
                self.assertEqual(sum(len(v[1])for v in value.values()),n*(n-1))
    def test_loading_failed_aborted_and_ordinary_single(self):
        for phase in ('loading','active','clear','failed'):
            self.compare(lambda a,d,r:setattr(r,'phase',phase))
        self.compare(lambda a,d,r:setattr(r,'aborted',True))
        self.compare(lambda a,d,r:setattr(r,'ordinary_travel',True),n=1)
    def test_stale_disabled_released_wrong_party_and_scene(self):
        mutations=[lambda a,d,r:a.registry.ids.remove(2),
            lambda a,d,r:a.playing.pop(2),lambda a,d,r:setattr(r.members[1],'released',True),
            lambda a,d,r:setattr(r.members[1],'coop_error',True),
            lambda a,d,r:setattr(r.members[1],'phase','town_ready'),
            lambda a,d,r:a.world.party_of.pop(r.members[1]),
            lambda a,d,r:r.party.update(run=None)]
        for f in mutations:self.compare(f)
    def test_departed_result_member_keeps_original_ports(self):
        def leave(a,d,r):
            r.phase='clear';s=r.members[1];d.rooms.pop(s);a.world.party_of.pop(s);s.phase='town_ready'
        _,_,r,value=self.compare(leave)
        self.assertNotIn(2,value);self.assertEqual(len(value),3)
        self.assertTrue(all(len(v[0]['peers'])==4 and len(v[1])==2 for v in value.values()))
    def test_last_dissolved_party_result_scene(self):
        def leave(a,d,r):
            r.phase='clear';s=r.members[0]
            for other in r.members[1:]:d.rooms.pop(other);a.world.party_of.pop(other);other.phase='town_ready'
            r.party['members']=[s];a.world.party_of.pop(s);a.world.parties.clear();s.clear_notified=True
        self.compare(leave)
    def test_revalidation_after_each_publication(self):
        a,d,r=fixture();self.assertEqual(len(d.routing(a,r)),4)
        a.registry.ids.remove(2);self.assertEqual(d.routing(a,r),{})
    def test_real_publication_routes_every_pair_once(self):
        rt=load('candidate_realtime_for_publication',ROOT/'source/els_server/realtime.py')
        a,d,r=fixture();a.config=NS(mode='friends')
        for s in r.members:s.shop_session_id='session'+str(s.identity['id']);s.social_overflow=False
        state=rt.RealtimeState()
        with patch.object(state,'transport_state',return_value=()),patch.object(rt,'context',return_value=None),patch('els_server.domain.session_auxiliary.friends_auxiliary_session',return_value=False),patch.object(d,'routing',wraps=d.routing)as batch:
            state.publish(a,lambda:None,())
            self.assertEqual(batch.call_count,1)
            self.assertEqual(len(state.view.manifests),4);self.assertEqual(len(state.view.routes),12)
            a.registry.ids.remove(2);state.publish(a,lambda:None,())
            self.assertFalse(state.view.routes)
    def test_batch_reduces_member_checks(self):
        a,d,r=fixture(4);counts={}
        with patch('els_server.domain.photo_zone_flow.manifest',return_value=None),patch('els_server.domain.photo_zone_flow.relay_target',return_value=None):
            for label,f in [('original',lambda:original(a,d,r)),('batch',lambda:d.routing(a,r))]:
                with patch.object(d,'_current_transport_member',wraps=d._current_transport_member)as spy:
                    started=time.perf_counter()
                    for _ in range(100):f()
                    counts[label]={'member_checks':spy.call_count//100,'ms_per_publication':(time.perf_counter()-started)*10}
        self.assertLess(counts['batch']['member_checks'],counts['original']['member_checks'])
        print(json.dumps(counts))
if __name__=='__main__':unittest.main(verbosity=2)
