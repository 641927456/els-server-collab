"""Same actual NPC conversations for selected runtime, public and local targets."""
import asyncio,struct
from achievement_protocol_client import connect
from els_server.domain.achievement_catalog import points
from els_server.protocol import achievement_messages as wire
from els_server.protocol.quest_messages import QUEST_REQUIREMENTS_NOT_MET

async def scenario(values,snapshot,report):
    peers=[]
    async def current():return await asyncio.to_thread(snapshot)
    try:
        for value in values:await connect(value,peers)
        a,b,c=peers;before=await current();assert all(row['days']==1 and not any(row['notes'].values())for row in before)
        reply=await c.query(0xfd,struct.pack('>i',10372));assert int.from_bytes(reply.payload[:4],'big',signed=True)==QUEST_REQUIREMENTS_NOT_MET
        await a.send(0xfd,struct.pack('>i',10018));await a.query(0x48d,reply=0x48f);assert await current()==before
        for npc,identity in zip(range(10372,10376),range(400,404)):
            start=len(a.received);reply=await a.query(0xfd,struct.pack('>i',npc));assert reply.payload[:4]==bytes(4)
            saved=await current();fresh=[r for r in saved[0]['achievement']['completed']if r['id']==identity];assert len(fresh)==1 and saved[0]['notes'][str(npc)]==1
            expected=wire.completion(fresh,points(saved[0]['achievement']['completed']),saved[0]['achievement']['watched'],False).payload
            assert any(e.kind==0x6c0 and e.payload==expected for e in a.received[start:])
        completed=await current();assert all(v==1 for v in completed[0]['notes'].values())and all(row['wallet']==old['wallet']for row,old in zip(completed,before))
        assert completed[1:]==before[1:]
        for _ in range(2):reply=await a.query(0xfd,struct.pack('>i',10372));assert reply.payload[:4]==bytes(4)
        await a.query(0x6be);await a.query(0x6be);assert await current()==completed
        reply=await a.query(0x6c1,struct.pack('>i',400));assert reply.payload[:4]==bytes(4)
        await a.close();peers.remove(a);await current();first=values[0]
        alt=await connect(dict(first,uid=first['alt_uid'],character_name=first['alt_name']),peers);await alt.query(0x6be);saved=(await current())[0]
        assert {400,401,402,403}<={r['id']for r in saved['alt_achievement']['completed']}and saved['alt_achievement']['watched']==[]and saved['achievement']['watched']==[400]and saved['days']==1
        old=await current();reply=await alt.query(0xfd,struct.pack('>i',10372));assert reply.payload[:4]==bytes(4)and await current()==old
        report.update(ok=True,checks=[*report.get('checks',[]),'Qualified Noah20012/scene1004FD/FE conversations commit four exact NPC sources and immediate400/401/402/403notifications','Wrong scene returns the original requirement refusal; unrelated NPC changes no notebook source','ED/items and both other accounts remain unchanged; repeated interaction and6BEreads settle once','Cold Noah sibling shares account completion and first-earner dedup with independent display; same-date count remains1'],retained_Noah_class_saved_room_level_ED_fixtures=True,natural_acquisition=False,native_Game=False,natural_GUI=False,production_clock_patch=False,connected_source_types=43,connected_definitions=257,remaining_source_types=17,unresolved_original_reward_groups=53,new_tables=0,new_indexes=0)
    finally:
        for p in reversed(peers):await p.close()
