"""Ten earlier class-independent regional cubes, with official weights.

Evidence chain: the official probability disclosure lists every reward and its
percentage for each cube; RandomItem.lua supplies the cube's group id and class
branch map; the client catalog supplies the Chinese name and record bytes for
each reward template. The Korean list and the template list are bound by
position, and the builder refuses to run unless the per-region counts, the
ascending order and the head-of-region anchor names all agree.
"""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data
@functools.lru_cache(maxsize=1)
def data():
 path=PROJECT_ROOT/'els_server/data/regional_boss_cubes_legacy.json';raw=path.read_bytes()
 checksum='28100c20b5171d1d0720904579338a7ffaa36934fd861bafdeeaa95dc4d04947'
 if hashlib.sha256(raw).hexdigest()!=checksum:raise ValueError('Legacy regional cube data changed')
 c=json.loads(raw)
 if c['client_sha256']!=CLIENT_SHA or c['source_catalog_sha256']!=client_data().manifest['catalog_sha256']:raise ValueError('Legacy regional cube build')
 for source in c['sources']:
  if hashlib.sha256((PROJECT_ROOT/source['path']).read_bytes()).hexdigest()!=source['sha256']:raise ValueError('Legacy regional cube evidence changed')
 if len(c['definitions'])!=10 or len(c['items'])!=86:raise ValueError('Legacy regional cube shape')
 for row in c['definitions']:
  if row['selection_count']!=0 or row['random'] is not True:raise ValueError('Legacy cube mode')
  if row['grant_source']!='regional_boss_cube':raise ValueError('Legacy cube grant source')
  if row['alternate_group']-row['primary_group']!=10:raise ValueError('Legacy cube paired group')
  if sum(entry['weight'] for entry in row['entries'])!=10000:raise ValueError('Legacy cube probability total')
  for entry in row['entries']:
   if hashlib.sha256(client_data().item(entry['template'])['record']).hexdigest()!=c['items'][str(entry['template'])]['record_sha256']:raise ValueError('Legacy reward identity')
 return c
def catalog():return {r['template']:r for r in data()['definitions']}
