"""Offline regression: real session handler and relay recovery with a virtual clock.

No listening sockets, game process, accounts, or player databases are created.
"""
from pathlib import Path
import sys,importlib.util,asyncio,json,types
from unittest.mock import patch
import argparse
p=argparse.ArgumentParser()
p.add_argument('--baseline-root',type=Path,required=True)
p.add_argument('--candidate-root',type=Path,required=True)
a=p.parse_args()
PARENT=a.baseline_root
CANDIDATE=a.candidate_root
sys.path.insert(0,str(PARENT));sys.dont_write_bytecode=True
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import LOCAL_TOWN_MAP,i32
import struct

def session_case(m,phase):
    a=m.LocalAccount();a.accept_terms();s=m.LocalSession(a,enter_town=True)
    for kind in [0x1a,0x1e,0x35,0x1ef,0x485]:s.handle(Event(0x202,kind=kind))
    if phase=='characters_ready':return s
    # Reconstruct the server phase from the archived request timeline. This
    # exercises the actual 0x490 handler without fabricating a player database.
    s.phase=phase;s.pending_map=LOCAL_TOWN_MAP
    s.completed.update((0x28,0x6e9,0x5bf,0x32))
    if phase in ('square_accepted','town_ready'):s.completed.add(0x225)
    if phase=='town_ready':s.completed.add(0x227)
    return s

base=module('baseline_local',PARENT/'els_server/domain/local_session.py')
fixed=module('candidate_local',CANDIDATE/'els_server/domain/local_session.py')
s=session_case(base,'square_accepted')
try:s.handle(Event(0x202,kind=0x490))
except base.SessionOrderError as e:assert 'outside phase square_accepted' in str(e)
else:raise AssertionError('Historical phase failure did not reproduce')
session_results=[]
for phase in ('square_accepted','town_ready','characters_ready'):
    s=session_case(fixed,phase);answer=s.handle(Event(0x202,kind=0x490))
    assert s.phase=='channels_ready' and answer[-1].kind==0x491
    if phase!='characters_ready':assert len(answer)==2
    duplicate=s.handle(Event(0x202,kind=0x490))
    assert s.phase=='channels_ready' and duplicate[-1]==answer[-1]
    session_results.append(dict(before=phase,after=s.phase,replies=[x.kind for x in answer]))
for phase,event in [('map_loading',Event(0x202,kind=0x490)),('square_accepted',Event(0x402,kind=0x490))]:
    s=session_case(fixed,phase)
    try:s.handle(event)
    except fixed.SessionOrderError:pass
    else:raise AssertionError('Unrelated phase/envelope boundary widened')
try:fixed.LocalSession().handle(Event(0x202,kind=0x490))
except fixed.SessionOrderError:pass
else:raise AssertionError('Unauthenticated channel access accepted')

async def recovery_case(m,kind,release_at=30.0):
    clock=[0.0];times=[];log=[]
    b=types.SimpleNamespace(closing=False,log=lambda event,**kw:log.append((event,kw)))
    c=m.RelayClient(b,reconnect=True);c.ever_ready=kind!='initial_busy'
    async def once():
        times.append(clock[0])
        if kind=='invalid':raise ValueError('Invalid relay frame')
        if kind=='initial_busy':raise m.RelayBusyError('Relay already connected')
        if len(times)==1 or kind=='network':raise ConnectionError('Dropped transport')
        if clock[0]<release_at:raise m.RelayBusyError('Relay already connected')
        b.closing=True
        raise asyncio.CancelledError()
    async def sleep(delay):clock[0]+=delay
    c._run_once=once
    outcome=''
    with patch.object(m,'time',types.SimpleNamespace(monotonic=lambda:clock[0])),patch.object(m.asyncio,'sleep',sleep):
        try:await c.run()
        except asyncio.CancelledError:outcome='reconnected'
        except Exception as e:outcome=type(e).__name__
    return dict(outcome=outcome,attempt_times=times,elapsed=clock[0])

async def relay_checks():
    baseline=module('baseline_relay',PARENT/'els_server/friends_relay.py')
    repaired=module('candidate_relay',CANDIDATE/'els_server/friends_relay.py')
    before=await recovery_case(baseline,'busy')
    after=await recovery_case(repaired,'busy')
    assert before['outcome']=='RelayUnavailableError' and before['elapsed']<30
    assert after['outcome']=='reconnected' and 30<=after['elapsed']<40
    assert len(after['attempt_times'])<=1+repaired.RECONNECT_ATTEMPTS
    persistent=await recovery_case(repaired,'busy',999)
    assert persistent['outcome']=='RelayUnavailableError' and len(persistent['attempt_times'])==6
    network=await recovery_case(repaired,'network')
    assert network['outcome']=='RelayUnavailableError' and network['elapsed']==before['elapsed']
    initial=await recovery_case(repaired,'initial_busy')
    invalid=await recovery_case(repaired,'invalid')
    assert initial['outcome']=='RelayBusyError' and initial['elapsed']==0
    assert invalid['outcome']=='ValueError' and invalid['elapsed']==0
    return dict(baseline=before,candidate=after,persistent_busy=persistent,ordinary_network=network,initial_busy=initial,invalid_packet=invalid)

result=dict(ok=True,session=session_results,relay=asyncio.run(relay_checks()),
    scope='Offline actual LocalSession handler plus virtual-clock RelayClient recovery; no native GUI acceptance, no network listeners or player data',
    baseline_failures_reproduced=2)
print(json.dumps(result,ensure_ascii=False))
