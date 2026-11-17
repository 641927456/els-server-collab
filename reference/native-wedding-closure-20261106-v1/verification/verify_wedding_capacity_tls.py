"""32 real protocol clients, reserved guest quota and production TLS fanout.

This is a server/transport qualification, not a32-slot native Game parse.
"""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
foundation=W/'verify_relationship_tls.py';original=foundation.read_text('utf8');tree=ast.parse(original)
main=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='main')
prefix='\n'.join(original.splitlines()[:main.lineno-1]);body=ast.get_source_segment(original,main)
cases=r'''
            from types import SimpleNamespace
            from els_server.protocol import wedding_messages as wedding
            from els_server.domain import wedding_rooms
            from els_server.friends_relay import read_packet,data_packet,read_data
            await groom.query(0x80d,struct.pack('>i',1))
            assert (await groom.query(0x80f,struct.pack('>IIH',1,1200277142,1))).payload[:4]==bytes(4)
            ring=read('SELECT uid FROM inventory_items WHERE owner=?AND template=277142',(uid[0],))[0][0]
            ends=(now//3600+1)*3600+86340
            invited=tuple(sorted(uid[2:15]))
            raw=struct.pack('>bbQQQB',5,4,ends,uid[1],ring,1)+wstring('三十二人联测')+wstring('')+struct.pack('>bI',13,len(invited))+b''.join(struct.pack('>Q',u)for u in invited)
            assert (await groom.query(0x887,raw)).payload[:4]==bytes(4)
            tickets={}
            for index in range(15):
                ids=[r[0]for r in read('SELECT mail_id FROM native_relationship_mail WHERE reservation=1 AND recipient_uid=?ORDER BY mail_id',(uid[index],))]
                claim=struct.pack('>I',len(ids))+b''.join(struct.pack('>Q',i)for i in ids)+bytes(6)
                assert (await peers[index].query(0x1d4,claim)).payload[:4]==bytes(4)
                tickets[uid[index]]=read('SELECT uid FROM inventory_items WHERE owner=?AND template IN(277151,277152)',(uid[index],))[0][0]
            def joining(role,ticket=0):return struct.pack('>bQiB',role,ticket,1,0)+wstring('')
            async def join(index,role):
                answer=await peers[index].query(0x88b,joining(role,tickets.get(uid[index],0)),reply=0x415)
                assert answer.payload[:4]==bytes(4),(index,answer.payload[:4].hex())
                return len(answer.payload)
            with patch.object(wedding_rooms,'time',SimpleNamespace(time=lambda:ends-86340,monotonic=time.monotonic)):
                await join(0,2);await join(1,2)
                for index in range(15,32):await join(index,3)
                room=app.world.weddings.room(app.playing[aid[0]])
                assert len(room.members)==19
                bad=await peers[32].query(0x88b,joining(3),reply=0x415)
                assert bad.payload[:4]!=bytes(4)and len(room.members)==19
                for index in range(2,15):last_bytes=await join(index,1)
                assert len(room.members)==32
                assert len({seat.index for seat in room.members.values()})==32
                manifest=await app.call(app.world.dungeons.manifest,app,aid[0])
                assert len(manifest['peers'])==32 and {p['port']for p in manifest['peers']}==set(range(21100,21132))
                initial={seat.uid:seat.index for seat in room.members.values()}
                assert (await peers[15].query(0x417,bytes(4))).payload[:4]==bytes(4)
                await join(32,3)
                assert len(room.members)==32
                assert room.members[app.playing[aid[32]]].index==initial[uid[15]]
                assert all(seat.index==initial[seat.uid]for seat in room.members.values()if seat.uid in initial)
                assert await app.call(app.world.dungeons.relay_target,app,aid[0],manifest['epoch'],uid[1])is None
                extra=await groom.query(0x88e,struct.pack('>iIQ',1,1,uid[15]))
                assert extra.payload[:4]==bytes(4)
                assert read('SELECT count FROM inventory_items WHERE owner=?AND template=277150',(uid[0],))==[(29,)]
                report['checks'].append('33 actual authenticated protocol clients:17 public guests exhaust only unreserved seats while13 invited guests still enter; full32-slot415 carries all roles/21100..21131; departure and replacement reuse only vacated slot and reject old epoch; current spouse88E invitation inside hall consumes one blank')
                relays=[]
                async def manifestation(reader):
                    async with asyncio.timeout(6):
                        while True:
                            packet=await read_packet(reader)
                            if packet[:1]==b'\1':
                                value=json.loads(packet[1:])
                                if value is not None and len(value['peers'])==32:return value
                try:
                    participants=[0,1,*range(2,15),*range(16,33)]
                    assert len(participants)==32
                    for index in participants:relays.append(await peers[index].bridge.remote(role='relay'))
                    manifests=await asyncio.gather(*(manifestation(reader)for reader,writer in relays))
                    epoch=manifests[0]['epoch'];assert all(m['epoch']==epoch for m in manifests)
                    for index in participants[1:]:
                        raw=data_packet(epoch,uid[index],b'owned-full-wedding-roster')
                        relays[0][1].write(struct.pack('>I',len(raw))+raw)
                    await relays[0][1].drain()
                    async def received(reader):
                        async with asyncio.timeout(6):
                            while True:
                                packet=await read_packet(reader)
                                if packet[:1]==b'\2':return read_data(packet)
                    delivered=await asyncio.gather(*(received(reader)for reader,writer in relays[1:]))
                    assert delivered==[(epoch,uid[0],b'owned-full-wedding-roster')]*31
                    report['checks'].append('32 real authenticated production TLS relay sockets publish the same current epoch; actual sender bytes reach all31 authorized peers with authoritative sender UID')
                    assert (await groom.query(0x41f)).payload[:4]==bytes(4);await bride.until(0x421)
                    answer=await bride.query(0x422,bytes((1,0)),reply=0x424)
                    assert answer.payload[:4]==bytes(4)and room.phase=='ceremony'
                    assert read('SELECT COUNT(*)FROM native_wedding_ceremonies')==[(1,)]
                    assert read("SELECT COUNT(*)FROM native_relationship_mail WHERE source LIKE 'wedding-complete:%'")==[(32,)]
                    assert read('SELECT COUNT(*)FROM inventory_items WHERE template IN(277151,277152)')==[(0,)]
                    assert not read('SELECT source FROM native_relationship_mail WHERE source LIKE ?AND recipient_uid=?',('wedding-complete:%',uid[15]))
                    report['checks'].append('Actual32-member mutual ceremony consumes15 exact participant tickets, commits one marriage and exactly32 participant letters; the departed guest gets no ceremony reward and its newly mailed invitation is not treated as a claimed ticket')
                finally:
                    for reader,writer in reversed(relays):
                        writer.close()
                        try:await writer.wait_closed()
                        except (ConnectionError,ssl.SSLError):pass
            report.update(server_full32_qualified=True,native_full32_parse_qualified=False,last_join_payload_bytes=last_bytes)
'''
start=body.index('            await groom.query(0xc09)');end=body.index("            report['ok']=True",start)
body=body[:start]+cases+body[end:]
body=body.replace("enumerate('AB')","enumerate(['A','B']+[str(i)for i in range(2,33)])")
body=body.replace("index+1,'owned-character-'","index%15+1,'owned-character-'")
body=body.replace('groom,bride=peers','groom,bride=peers[:2]').replace('RelationTLS','Hall')
body=body.replace('base=int(datetime.combine(day,daytime(hour=12),CLIENT_ZONE).timestamp())','base=now-60')
body=body.replace("port=0,state_file=", "port=0,max_connections=192,state_file=")
body=body.replace("report['ok']=True", "report.update(configured_connection_capacity=192,connection_capacity_matches_current_local_private_config=True);report['ok']=True")
body=body.replace("'owned-relationship-tls-'","'owned-wedding-capacity-tls-'").replace("'relationship-tls-'","'wedding-capacity-tls-'")
generated=W/'generated-wedding-capacity-tls.py';ast.parse(body);generated.write_text(body+'\n','utf8')
exec(compile(prefix,str(foundation),'exec'),globals());exec(compile(body,str(generated),'exec'),globals())
if __name__=='__main__':
    # A real client reads unsolicited peer/periodic packets continuously.
    # The small four-client helper reads only while waiting for a query; at
    # this scale its dormant readers can backpressure the TLS output path.
    # Keep the same25s request limit and all normal production periodic work.
    from native_peer import Peer
    from els_server.protocol.protocol_codec import decode_event,decode_frame
    original_close=Peer.close
    async def receive(peer):
        try:
            while True:
                head=await peer.reader.readexactly(8)
                raw=head+await peer.reader.readexactly(struct.unpack_from('<I',head)[0]-8)
                event=decode_event(decode_frame(raw,peer.keys,expected_sequence=peer.incoming).plaintext)
                peer.incoming+=1;peer.received.append(event);peer._qa_queue.put_nowait(event)
        except (asyncio.IncompleteReadError,ConnectionError):return
    async def until(peer,kind):
        if not hasattr(peer,'_qa_queue'):
            peer._qa_queue=asyncio.Queue();peer._qa_receiver=asyncio.create_task(receive(peer))
        async with asyncio.timeout(25):
            for _ in range(400):
                event=await peer._qa_queue.get()
                if event.kind==kind:return event
        raise AssertionError('Native reply missing '+hex(kind))
    async def close(peer):
        try:return await original_close(peer)
        finally:
            if hasattr(peer,'_qa_receiver'):
                peer._qa_receiver.cancel();await asyncio.gather(peer._qa_receiver,return_exceptions=True)
    with patch.object(Peer,'until',until),patch.object(Peer,'close',close):
        raise SystemExit(not asyncio.run(main()))
