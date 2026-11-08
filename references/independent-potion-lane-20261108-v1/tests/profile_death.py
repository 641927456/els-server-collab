"""Profile genuine death consumers using an owned, synthetic character."""
import asyncio,contextlib,cProfile,json,pstats,struct,time
from pathlib import Path
import runtime_fixture as h
import sqlite3
from els_server.storage.characters import Characters
from els_server.storage.seal_quests import QuestState
from els_server.storage.inventory_state import load_items,grant_items
from els_server.game_data import client_data
from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
from els_server.protocol.protocol_codec import Event

def seed(c):
    uid=Characters(c.config.state_file,c.alice['id']).create('OwnPotion',5,'owned-potion-latency')['uid']
    QuestState(c.config.state_file,uid,account_id=c.alice['id']).snapshot()
    with contextlib.closing(sqlite3.connect(c.config.state_file)) as db,db:
        db.execute('UPDATE characters SET level=99,unit_class=164,transcendence=1,master=1,revision=revision+1 WHERE uid=?',(uid,))
        db.execute('INSERT INTO character_artifacts VALUES (?,?,1,1,0,?)',(uid,5,json.dumps([0]*4)))
        db.execute('UPDATE reward_balances SET experience=? WHERE uid=?',(client_data().thresholds[98],uid))
        from els_server.storage.resonance_state import ensure
        ensure(db)
        db.execute('INSERT INTO account_resonance VALUES (?,1,0,1)',(c.alice['id'],))
        for q in (26660,26680):
            db.execute('DELETE FROM character_quests WHERE owner=? AND quest=?',(uid,q))
            db.execute('INSERT OR IGNORE INTO completed_quests VALUES(?,?,?,?)',(uid,q,1,'{}'))
        items=load_items(db,uid)
        item=next(i for i in items if TEMPLATE_BAG_GROUPS[i['template']]in(7,27)and TEMPLATE_MAX_STACKS[i['template']]==1)
        grant_items(db,[dict(template=item['template'],metadata=item['metadata'],group=TEMPLATE_BAG_GROUPS[item['template']],quantity=350-len(items))],uid)
        from els_server.domain.seal_quests import quest_catalog
        for q in json.loads((h.H/'fixture-shape.json').read_bytes())['quests']:
            objectives={str(s['m_iID']):0 for s in quest_catalog().objectives(q)}
            db.execute('INSERT OR REPLACE INTO character_quests VALUES(?,?,1,1,?)',(uid,q,json.dumps(objectives)))
    return uid

def death(npc,uid):
    payload=(struct.pack('>iBQQ6fBf',npc['key'],0,uid,uid,0.,0.,0.,1.,2.,3.,0,npc['hp'])
        +struct.pack('>IQf',1,uid,1.)+struct.pack('>IQB',1,uid,1)+bytes(8)+bytes(4)+struct.pack('>Q',uid))
    return Event(0x202,performers=(0,),kind=0xad,payload=payload)

async def main():
    c=h.f.FriendsTests();await c.asyncSetUp();result=dict(ok=False,profiles=[],owned_fixture=True)
    try:
        uid=seed(c);peer=await c.peer(c.alice);await peer.roster();await peer.enter_town(uid)
        s=c.app.playing[c.alice['id']];run=h.room(s)
        npcs=[n for n in run.current['npcs'] if n['active'] and not n['no_drop'] and not n.get('ally')]
        assert len(npcs)>=3
        original=s.handle
        from unittest.mock import patch
        current=None
        def handle(event,request_sequence=None):
            p=cProfile.Profile();started=time.perf_counter();p.enable()
            try:return original(event,request_sequence=request_sequence)
            finally:
                p.disable();rows=[]
                for (file,line,function),(primitive,calls,own,total,_) in pstats.Stats(p).stats.items():
                    rows.append(dict(file=file,line=line,function=function,calls=calls,self_ms=own*1000,cumulative_ms=total*1000))
                result['profiles'].append(dict(kind=event.kind,total_ms=(time.perf_counter()-started)*1000,rows=sorted(rows,key=lambda r:r['cumulative_ms'],reverse=True)))
        # Keep FriendsSession.handle identity for normal routing and profile
        # its worker call without replacing the bound routing entry point.
        original_class=type(s).handle
        def wrapper(self,event,request_sequence=None):
            return handle(event,request_sequence) if self is s else original_class(self,event,request_sequence)
        wrapper.__name__='handle'
        with patch.object(type(s),'handle',wrapper):
            for index,npc in enumerate(npcs[:3]):
                events=await c.app.call(s.handle,death(npc,uid),request_sequence=2000+index)
                assert any(e.kind==0xae for e in events),[e.kind for e in events]
        assert len(run.defeated)==3
        result['ok']=True
    finally:
        await c.asyncTearDown();result['cleaned']=not c.root.exists()
        suffix='candidate'if'--candidate'in h.sys.argv else'baseline'
        (h.H/('profile-death-'+suffix+'.json')).write_text(json.dumps(result,indent=2)+'\n','utf8')
    print(json.dumps(dict(ok=result['ok'],cleaned=result['cleaned'],profiles=[dict(total_ms=p['total_ms'],top=p['rows'][:12],self_top=sorted(p['rows'],key=lambda r:r['self_ms'],reverse=True)[:7]) for p in result['profiles']]),ensure_ascii=True))

if __name__=='__main__':asyncio.run(main())
