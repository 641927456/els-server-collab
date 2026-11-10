"""Production TLS relay loss and deadline/cold paths; explicit owned clocks."""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
foundation=W/'verify_relationship_tls.py';original=foundation.read_text('utf8');tree=ast.parse(original)
main=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main')
prefix='\n'.join(original.splitlines()[:main.lineno-1]);body=ast.get_source_segment(original,main)
room_tree=ast.parse((W/'verify_wedding_rooms_tls.py').read_text('utf8'))
room_cases=ast.literal_eval(next(n.value for n in room_tree.body if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='cases'for t in n.targets)))
setup=room_cases[:room_cases.index("            before=read(")]
cases=r'''
            from els_server.friends_relay import read_packet,data_packet,read_data
            from els_server.storage import wedding_ceremonies
            from els_server.protocol import dungeon_messages
            relays=[]
            async def manifestation(reader,count):
                async with asyncio.timeout(5):
                    while True:
                        packet=await read_packet(reader)
                        if packet[:1]==b'\1':
                            value=json.loads(packet[1:])
                            if value is not None and len(value['peers'])==count:return value
            async def return_town(peer,*,notice=False):
                if notice:await peer.until(0x418)
                xyz=catalog()['towns']['20001']['xyz']
                assert (await peer.query(0x225,struct.pack('>iB',20001,0))).payload[:4]==bytes(4)
                assert (await peer.query(0x227,struct.pack('>fffBH',*xyz,0,0))).payload[:4]==bytes(4)
            try:
                with patch.object(wedding_rooms,'time',SimpleNamespace(time=lambda:ends-86340,monotonic=time.monotonic)):
                    for peer,person,role in((groom,uid[0],2),(bride,uid[1],2),(peers[2],uid[2],1)):
                        assert (await peer.query(0x88b,joining(role,tickets[person]),reply=0x415)).payload[:4]==bytes(4)
                room=app.world.weddings.room(app.playing[aid[0]])
                for peer in peers[:3]:relays.append(await peer.bridge.remote(role='relay'))
                manifests=[await manifestation(reader,3)for reader,writer in relays]
                assert len({m['epoch']for m in manifests})==1
                epoch=manifests[0]['epoch']
                raw=data_packet(epoch,uid[1],b'owned-wedding-native-datagram')
                relays[0][1].write(struct.pack('>I',len(raw))+raw);await relays[0][1].drain()
                async with asyncio.timeout(5):
                    while True:
                        packet=await read_packet(relays[1][0])
                        if packet[:1]==b'\2':break
                assert read_data(packet)==(epoch,uid[0],b'owned-wedding-native-datagram')
                reader,writer=relays.pop();writer.close();await writer.wait_closed()
                await return_town(peers[2],notice=True)
                assert app.world.weddings.room(app.playing[aid[2]])is None and len(room.members)==2
                assert read('SELECT uid FROM inventory_items WHERE uid=?',(tickets[uid[2]],))
                assert await app.call(app.world.dungeons.relay_target,app,aid[0],epoch,uid[1])is None
                report['checks'].append('Actual authenticated production TLS relay forwards native bytes between current wedding peers; guest relay socket close sends native418/return to town, retains unused invitation ticket and fences old epoch')
                # Execute only the existing deadline worker under its normal
                # App lane; clock and encoder failure are explicit fixtures.
                def expire_room(fail=False):
                    with patch.object(wedding_rooms,'time',SimpleNamespace(time=lambda:ends+60,monotonic=time.monotonic)):
                        if fail:
                            with patch.object(dungeon_messages,'return_user_sync',side_effect=ValueError('Owned late deadline return encoder')):
                                return app.world.weddings.periodic(app.playing[aid[0]])
                        return app.world.weddings.periodic(app.playing[aid[0]])
                try:await app.call(expire_room,True)
                except ValueError as error:assert str(error)=='Owned late deadline return encoder'
                else:raise AssertionError('Deadline late encoder accepted')
                assert read('SELECT finished_at FROM native_wedding_bookings')==[(None,)]
                assert len(room.members)==2 and len(read('SELECT mail_id FROM native_relationship_mail'))==8
                await app.call(expire_room)
                for peer in(groom,bride):await return_town(peer,notice=True)
                assert not app.world.weddings.rooms and not app.world.weddings.by_session
                assert read('SELECT mode,at FROM native_wedding_ceremonies')==[('deadline',ends+60)]
                assert len(read('SELECT mail_id FROM native_relationship_mail'))==8
                assert len(read('SELECT uid FROM inventory_items WHERE template IN(277151,277152)'))==3
                report['checks'].append('Production deadline worker: late return encoding rolls back marriage and retains room; exact24hour expiry commits one deadline marriage and native890/418 returns both spouses, with no ceremony gifts or ticket debit')
                # A second reminder closes while both spouses are outside a
                # hall. It cannot renew the first marriage or participation mail.
                await groom.query(0x80d,struct.pack('>i',1))
                assert (await groom.query(0x80f,struct.pack('>IIH',1,1200277141,1))).payload[:4]==bytes(4)
                ring2=read('SELECT uid FROM inventory_items WHERE owner=?AND template=277141',(uid[0],))[0][0]
                end2=ends+3600
                raw2=struct.pack('>bbQQQB',2,0,end2,uid[1],ring2,1)+wstring('到期提醒')+wstring('')+struct.pack('>bI',0,0)
                assert (await groom.query(0x887,raw2)).payload[:4]==bytes(4)
                def outside_deadline():
                    s=app.playing[aid[0]];s.wedding_deadline_after=0
                    with patch.object(wedding_rooms,'time',SimpleNamespace(time=lambda:end2+60,monotonic=time.monotonic)):
                        app.world.weddings.periodic(s)
                await app.call(outside_deadline)
                assert read('SELECT mode,at FROM native_wedding_ceremonies ORDER BY reservation')==[('deadline',ends+60),('deadline',end2+60)]
                for a in aid[:2]:
                    state=app.playing[a].account.character()['relationship']
                    assert state['created_at']==state['refreshed_at']==ends+60
                count=len(read('SELECT mail_id FROM native_relationship_mail'))
                await app.call(outside_deadline)
                assert len(read('SELECT mail_id FROM native_relationship_mail'))==count
                report['checks'].append('Outside-hall periodic deadline completes the reminder once and notifies current spouses; it preserves the first marriage/refresh dates and adds no participation letters on replay')
                # A separate C/D couple is an explicit accepted-source fixture.
                # Cold initialization itself must settle the expired booking.
                with closing(sqlite3.connect(cfg.state_file))as db,db:
                    grant_items(db,[dict(template=269710,metadata=0,group=4,quantity=1),dict(template=277142,metadata=0,group=4,quantity=1)],uid[2])
                    relationships.propose(db,uid[2],aid[2],uid[3],aid[3],'cold-c','cold-d',rel.descriptor('RelationTLSD'),
                        'owned-cold-propose',guard=lambda db:None,encode=lambda *args:[],now=now)
                    raw_accept=struct.pack('>bQ',0,uid[2])+wstring('RelationTLSC')+struct.pack('>QBH',0,0,0)+struct.pack('>Q',uid[3])+wstring('RelationTLSD')+bytes(1)+rel.descriptor('RelationTLSD')
                    relationships.answer(db,uid[3],aid[3],uid[2],aid[2],'cold-d','cold-c',raw_accept,'owned-cold-accept',guard=lambda db:None,encode=lambda *args:[],now=now)
                ring3=read('SELECT uid FROM inventory_items WHERE owner=?AND template=277142',(uid[2],))[0][0]
                raw3=struct.pack('>bbQQQB',2,0,ends,uid[3],ring3,1)+wstring('离线到期')+wstring('')+struct.pack('>bI',0,0)
                c=peers[2];d=peers[3]
                assert (await c.query(0x887,raw3)).payload[:4]==bytes(4)
                cold_count=len(read('SELECT mail_id FROM native_relationship_mail'))
                old={a:app.playing[a]for a in aid[2:]}
                for peer in(c,d):await peer.close();peers.remove(peer)
                deadline=time.monotonic()+5
                while any(app.playing.get(a)is s for a,s in old.items()):
                    assert time.monotonic()<deadline;await asyncio.sleep(.01)
                with patch.object(wedding_ceremonies,'time',SimpleNamespace(time=lambda:ends+60)):
                    c=await connect(values[2],peers)
                assert app.playing[aid[2]].account.character()['relationship']['kind']==2
                assert read('SELECT mode,at FROM native_wedding_ceremonies WHERE reservation=3')==[('deadline',ends+60)]
                assert len(read('SELECT mail_id FROM native_relationship_mail'))==cold_count
                report['checks'].append('Actual cold28 initialization of a separately accepted couple settles an offline expired reservation before original cold projection; marriage kind2 restores without ceremony gifts')
            finally:
                for reader,writer in reversed(relays):
                    writer.close()
                    try:await writer.wait_closed()
                    except (ConnectionError,ssl.SSLError):pass
            report.update(deadline_clocks_are_explicit_fixtures=True,native_Game=False,natural_GUI=False)
'''
start=body.index('            await groom.query(0xc09)');end=body.index("            report['ok']=True",start)
body=body[:start]+setup+cases+body[end:]
body=body.replace("enumerate('AB')","enumerate('ABCD')").replace('groom,bride=peers','groom,bride=peers[:2]')
body=body.replace('base=int(datetime.combine(day,daytime(hour=12),CLIENT_ZONE).timestamp())','base=now-60')
body=body.replace("'owned-relationship-tls-'","'owned-wedding-deadlines-tls-'").replace("'relationship-tls-'","'wedding-deadlines-tls-'")
generated=W/'generated-wedding-deadlines-tls.py';ast.parse(body);generated.write_text(body+'\n','utf8')
exec(compile(prefix,str(foundation),'exec'),globals());exec(compile(body,str(generated),'exec'),globals())
if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
