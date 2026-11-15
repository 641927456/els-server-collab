"""Original eight-person studio lifecycle plus one-publication authority checks."""
from pathlib import Path
import ast
W=Path(__file__).resolve().parent
source=(W.parent/'independent-delivery-v4/verify_photo_tls.py').read_text('utf8')
needle="                assert len(room['members'])==8 and set(room['ports'].values())==set(range(8))"
addition='''
                def snapshot_check():
                    from unittest.mock import patch
                    from els_server.domain import photo_zone_flow as flow
                    called=[];actual=flow._capture
                    def capture(s):called.append(s);return actual(s)
                    with patch.object(flow,'_capture',side_effect=capture):
                        app.realtime.publish(app,lambda:None,())
                    assert len(called)==8 and set(called)==set(room['members'])
                    expected={(p.account.account_id,room['epoch'],other.account.uid):(other.account.account_id,p.account.uid)
                        for p in room['members']for other in room['members']if other is not p}
                    assert dict(app.realtime.view.routes)==expected and len(expected)==56
                    victim=live(4);token=victim.shop_session_id
                    try:
                        victim.shop_session_id=str(__import__('uuid').uuid4())
                        app.realtime.publish(app,lambda:None,())
                        assert not app.realtime.view.routes
                        assert not any(identities[i]['id']in app.realtime.view.manifests for i in range(8))
                    finally:victim.shop_session_id=token
                    app.realtime.publish(app,lambda:None,())
                    assert dict(app.realtime.view.routes)==expected
                await app.call(snapshot_check)
                report['checks'].append('One studio publication runs all8 original authority captures exactly once, builds56 directed routes, rejects a changed admitted session generation and rebuilds valid routes on the next publication')
'''
assert needle in source
source=source.replace(needle,needle+addition)
source=source.replace("'private-TLS-'","'photo-routing-TLS-'")
ast.parse(source)
exec(compile(source,str(W.parent/'independent-delivery-v4/verify_photo_tls.py'),'exec'),globals())
