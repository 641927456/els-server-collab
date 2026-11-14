"""Actual four-role rooms: publication reuse retains the original authority."""
from pathlib import Path
import ast

W = Path(__file__).resolve().parent
source = (W / 'verify_wedding_rooms_tls.py').read_text('utf8')
needle = "                manifest=await app.call(app.world.dungeons.manifest,app,aid[0])"
cases = '''                def routing_snapshot():
                    called=[]
                    actual=app.world.weddings.capture
                    def capture(p):
                        called.append(p)
                        return actual(p)
                    with patch.object(app.world.weddings,'capture',side_effect=capture):
                        app.realtime.publish(app,lambda:None,())
                    assert len(called)==4 and set(called)==set(room.members)
                    view=app.realtime.view
                    expected={(seat.owner,room.epoch,other.uid):(other.owner,seat.uid)
                        for p,seat in room.members.items()for other in room.members.values()if other.actor is not p}
                    assert dict(view.routes)==expected and len(expected)==12
                    assert all(json.loads(view.manifests[a][1:])['uid']==u for a,u in zip(aid,uid))
                    victim=app.playing[aid[2]]
                    token=victim.shop_session_id
                    try:
                        victim.shop_session_id=__import__('uuid').uuid4().hex
                        app.realtime.publish(app,lambda:None,())
                        assert not app.realtime.view.routes
                        assert not any(a in app.realtime.view.manifests for a in aid)
                    finally:victim.shop_session_id=token
                    app.realtime.publish(app,lambda:None,())
                    assert dict(app.realtime.view.routes)==expected
                    phase=victim.phase
                    try:
                        victim.phase='town_ready'
                        app.realtime.publish(app,lambda:None,())
                        assert not app.realtime.view.routes
                    finally:victim.phase=phase
                    app.realtime.publish(app,lambda:None,())
                    assert dict(app.realtime.view.routes)==expected
                await app.call(routing_snapshot)
                report['checks'].append('One production publication performs all four original capture/reset-authority checks exactly once and derives12 directed routes with no self-route; changed session generation or phase revokes the entire current roster on the next publication, then valid state repopulates without a persistent cache')
'''
assert needle in source
source = source.replace(needle, cases + needle)
source = source.replace("'owned-wedding-rooms-tls-'", "'owned-wedding-transport-snapshot-tls-'")
source = source.replace("'wedding-rooms-tls-'", "'wedding-transport-snapshot-tls-'")
source = source.replace('generated-wedding-rooms-tls.py', 'generated-wedding-transport-snapshot-tls.py')
ast.parse(source)
exec(compile(source, str(W / 'verify_wedding_rooms_tls.py'), 'exec'), globals())
