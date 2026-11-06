"""Actual authenticated wedding room/consent/return path, private fixtures."""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
foundation=W/'verify_relationship_tls.py';original=foundation.read_text('utf8');tree=ast.parse(original)
main=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main')
prefix='\n'.join(original.splitlines()[:main.lineno-1])
body=ast.get_source_segment(original,main)
start=body.index('            await groom.query(0xc09)')
end=body.index("            report['ok']=True",start)
cases=r'''
            from types import SimpleNamespace
            from els_server.protocol import wedding_messages as wedding
            from els_server.domain import wedding_rooms
            await groom.query(0x80d,struct.pack('>i',1))
            assert (await groom.query(0x80f,struct.pack('>IIH',1,1200277142,1))).payload[:4]==bytes(4)
            ring=read('SELECT uid FROM inventory_items WHERE owner=?AND template=277142',(uid[0],))[0][0]
            ends=(now//3600+1)*3600+86340
            raw=struct.pack('>bbQQQB',5,4,ends,uid[1],ring,0)+wstring('房间联测')+wstring('privateRoom77')+struct.pack('>bIQ',13,1,uid[2])
            assert (await groom.query(0x887,raw)).payload[:4]==bytes(4)
            for peer,owner in zip(peers,uid):
                ids=[r[0]for r in read('SELECT mail_id FROM native_relationship_mail WHERE reservation=1 AND recipient_uid=?ORDER BY mail_id',(owner,))]
                if ids:
                    claim=struct.pack('>I',len(ids))+b''.join(struct.pack('>Q',i)for i in ids)+bytes(6)
                    assert (await peer.query(0x1d4,claim)).payload[:4]==bytes(4)
            tickets={person:read('SELECT uid FROM inventory_items WHERE owner=?AND template IN(277151,277152)',(person,))[0][0]for person in uid[:3]}
            def joining(role,ticket=0,password=''):
                return struct.pack('>bQiB',role,ticket,1,0)+wstring(password)
            before=read('SELECT uid,owner,template,count FROM inventory_items ORDER BY uid')
            assert (await groom.query(0x88b,joining(2,tickets[uid[0]]),reply=0x415)).payload[:4]!=bytes(4)
            assert not app.world.weddings.rooms
            # Explicit future-clock fixture; all sessions and mail/tickets are
            # actual App/TLS products. No reserved-date SQL is rewritten.
            with patch.object(wedding_rooms,'time',SimpleNamespace(time=lambda:ends-86340,monotonic=time.monotonic)):
                assert (await peers[2].query(0x88b,joining(2,tickets[uid[0]]),reply=0x415)).payload[:4]!=bytes(4)
                assert (await groom.query(0x88b,joining(2,tickets[uid[0]]),reply=0x415)).payload[:4]==bytes(4)
                room=app.world.weddings.room(app.playing[aid[0]])
                assert room is not None and room.world==903
                assert (await groom.query(0x41f)).payload[:4]!=bytes(4)
                assert (await bride.query(0x88b,joining(2,tickets[uid[1]]),reply=0x415)).payload[:4]==bytes(4)
                assert (await peers[2].query(0x88b,joining(1,tickets[uid[2]]),reply=0x415)).payload[:4]==bytes(4)
                assert (await peers[3].query(0x88b,joining(3,password='wrong'),reply=0x415)).payload[:4]!=bytes(4)
                assert (await peers[3].query(0x88b,joining(3,password='privateRoom77'),reply=0x415)).payload[:4]==bytes(4)
                assert len(room.members)==4 and sorted(x.role for x in room.members.values())==[1,2,3,4]
                assert read('SELECT uid,owner,template,count FROM inventory_items ORDER BY uid')==before
                assert read('SELECT town FROM location ORDER BY uid')==[(20001,)]*4
                assert all(app.playing[a]not in app.world.members for a in aid)
                assert (await peers[2].query(0x41f)).payload[:4]!=bytes(4)
                report['checks'].append('Actual88B refuses unopened/foreign spouse/wrong password; saved spouses, invited ticket and password guest enter original415/416 with four native roles; no entry ticket debit or saved-town overwrite; guest/missing-spouse start refuses')
                manifest=await app.call(app.world.dungeons.manifest,app,aid[0])
                assert len(manifest['peers'])==4 and {p['port']for p in manifest['peers']}=={21100,21101,21102,21103}
                assert await app.call(app.world.dungeons.relay_target,app,aid[0],manifest['epoch'],uid[1])==(aid[1],uid[0])
                assert await app.call(app.world.dungeons.relay_target,app,aid[0],manifest['epoch'],uid[0])is None
                assert (await groom.query(0x41f)).payload[:4]==bytes(4)
                await bride.until(0x421)
                assert (await bride.query(0x422,bytes(2),reply=0x423)).payload==bytes(2)
                assert room.pending is None and not read('SELECT finished_at FROM native_wedding_bookings WHERE finished_at IS NOT NULL')
                assert (await groom.query(0x41f)).payload[:4]==bytes(4)
                await bride.until(0x421)
                old=app.playing[aid[1]];await bride.close();peers.remove(bride)
                deadline=time.monotonic()+5
                while app.playing.get(aid[1])is old:
                    assert time.monotonic()<deadline;await asyncio.sleep(.01)
                assert room.pending is None and len(room.members)==3
                assert await app.call(app.world.dungeons.relay_target,app,aid[0],manifest['epoch'],uid[2])is None
                bride=await connect(values[1],peers)
                assert (await bride.query(0x88b,joining(2,tickets[uid[1]]),reply=0x415)).payload[:4]==bytes(4)
                assert len(room.members)==4 and room.members[app.playing[aid[1]]].index==1
                report['checks'].append('Production manifest/route has four authenticated current peers; refusal clears consent; real spouse TLS disconnect cancels pending consent and fences old epoch, then authenticated reconnect reuses spouse slot without losing ticket')
                assert (await groom.query(0x41f)).payload[:4]==bytes(4)
                await bride.until(0x421)
                oldwire=wedding.ceremony_started
                def fail(changes=(),*,refresh=False,result=0):
                    if result==0:raise ValueError('Owned late424 encoding failure')
                    return oldwire(changes,refresh=refresh,result=result)
                with patch.object(wedding,'ceremony_started',side_effect=fail):
                    bad=await bride.query(0x422,bytes((1,0)),reply=0x424)
                assert bad.payload[:4]!=bytes(4) and room.phase=='waiting'and room.pending is not None
                assert read('SELECT uid,owner,template,count FROM inventory_items ORDER BY uid')==before
                assert read('SELECT finished_at FROM native_wedding_bookings')==[(None,)]
                assert len(read('SELECT mail_id FROM native_relationship_mail'))==8
                good=await bride.query(0x422,bytes((1,0)),reply=0x424)
                assert good.payload[:4]==bytes(4)and room.phase=='ceremony'and room.pending is None
                assert not read('SELECT uid FROM inventory_items WHERE template IN(277151,277152)')
                assert len(read('SELECT mail_id FROM native_relationship_mail'))==12
                assert read('SELECT COUNT(*)FROM native_wedding_ceremonies')==[(1,)]
                await bride.send(0x422,bytes((1,0)));await bride.send(0x48d);await bride.until(0x48f)
                assert len(read('SELECT mail_id FROM native_relationship_mail'))==12
                assert read('SELECT COUNT(*)FROM native_wedding_ceremonies')==[(1,)]
                report['checks'].append('Actual41F/421/422/423/424 mutual consent: late424 failure retains tickets, reservation, pending consent and8 mails; success consumes three exact tickets, records one marriage and issues four correct participant letters; repeated consent adds nothing')
                # Real native return requests after418, preserving each source.
                for peer in list(peers):
                    assert (await peer.query(0x417,bytes(4))).payload[:4]==bytes(4)
                    xyz=catalog()['towns']['20001']['xyz']
                    assert (await peer.query(0x225,struct.pack('>iB',20001,0))).payload[:4]==bytes(4)
                    assert (await peer.query(0x227,struct.pack('>fffBH',*xyz,0,0))).payload[:4]==bytes(4)
                assert not app.world.weddings.rooms and not app.world.weddings.by_session
                assert all(app.playing[a].phase=='town_ready'and app.playing[a]in app.world.members for a in aid)
                assert (await groom.query(0x88b,joining(2,tickets[uid[0]]),reply=0x415)).payload[:4]!=bytes(4)
            for account in aid[:2]:
                projection=app.playing[account].account.character()['relationship']
                assert projection['kind']==2 and projection['created_at']==projection['refreshed_at']==ends-86340
            old=app.playing[aid[0]];await groom.close();peers.remove(groom)
            deadline=time.monotonic()+5
            while app.playing.get(aid[0])is old:
                assert time.monotonic()<deadline;await asyncio.sleep(.01)
            groom=await connect(values[0],peers)
            assert app.playing[aid[0]].account.character()['relationship']['kind']==2
            assert len(read('SELECT mail_id FROM native_relationship_mail'))==12
            report['checks'].append('Actual417/418/F3 then225/227 returns every participant to original town, clears room/relay membership, rejects post-start reentry; authenticated cold reconnect keeps marriage kind2 and12 original letters')
            report.update(room_clock_is_explicit_future_fixture=True,native_Game=False,natural_GUI=False)
'''
body=body[:start]+cases+body[end:]
body=body.replace("enumerate('AB')","enumerate('ABCD')").replace('groom,bride=peers','groom,bride=peers[:2]')
body=body.replace('base=int(datetime.combine(day,daytime(hour=12),CLIENT_ZONE).timestamp())','base=now-60')
body=body.replace("'owned-relationship-tls-'","'owned-wedding-rooms-tls-'").replace("'relationship-tls-'","'wedding-rooms-tls-'")
generated=W/'generated-wedding-rooms-tls.py';ast.parse(body);generated.write_text(body+'\n','utf8')
exec(compile(prefix,str(foundation),'exec'),globals());exec(compile(body,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
