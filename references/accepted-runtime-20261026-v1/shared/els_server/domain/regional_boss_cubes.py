"""Three original class-independent regional cubes, with official weights."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data
@functools.lru_cache(maxsize=1)
def data():
 path=PROJECT_ROOT/'els_server/data/regional_boss_cubes.json';raw=path.read_bytes()
 checksum='49c1dbdb993b6912d4bb27c2b9ff4442856dc0bbf459dd920cd188707cebef01'
 if hashlib.sha256(raw).hexdigest()!=checksum:raise ValueError('Regional cube data changed')
 c=json.loads(raw)
 if c['client_sha256']!=CLIENT_SHA or c['source_catalog_sha256']!=client_data().manifest['catalog_sha256']:raise ValueError('Regional cube build')
 for source in c['sources']:
  if hashlib.sha256((PROJECT_ROOT/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Regional cube evidence changed')
 p=json.loads((PROJECT_ROOT/'analysis/sol-high-20261015/equipment-ui/regional-boss-items-native.json').read_text())
 if not p['all_passed'] or p['live_process_access'] is not False or p['catalog_sha256']!=checksum or len(p['rows'])!=len(c['items']):raise ValueError('Regional cube native proof')
 for row in p['rows']:
  item=c['items'][str(row['template'])]
  if row['native_group']!=item['group'] or hashlib.sha256(client_data().item(item['template'])['record']).hexdigest()!=item['record_sha256']:raise ValueError('Regional item identity')
 return c
def catalog():return {r['template']:r for r in data()['definitions']}
def draw(row,roll):
 if type(roll) is not int or not 0<=roll<10000:raise ValueError('Cube random range')
 for entry in row['entries']:
  if roll<entry['weight']:return entry
  roll-=entry['weight']
 raise ValueError('Cube probability total')
