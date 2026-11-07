"""Project committed owned-room facts in the housing business transaction."""
from els_server.storage.achievement_profiles import reconcile
from els_server.storage.achievements import snapshot
from els_server.domain.achievement_catalog import points
from els_server.protocol.achievement_messages import completion

def update(db,owner,account,stamp):
 result=reconcile(db,account,owner,stamp,condition_types=frozenset((64,65)))
 if not result['completed']:return []
 current=snapshot(db,account,owner);fresh=set(result['completed'])
 return[completion([r for r in current['completed']if r['id']in fresh],points(current['completed']),current['watched'],False)]
