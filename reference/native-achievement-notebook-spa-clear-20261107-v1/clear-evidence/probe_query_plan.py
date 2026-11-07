"""Isolated SQLite expression-affinity comparison; no application saves."""
from pathlib import Path
import json,sqlite3
F=Path(__file__).resolve().parent;db=sqlite3.connect(':memory:')
db.executescript('CREATE TABLE owners(uid INTEGER PRIMARY KEY,account INTEGER);CREATE INDEX oa ON owners(account);CREATE TABLE receipts(id TEXT PRIMARY KEY,j TEXT);')
db.executemany('INSERT INTO owners VALUES (?,?)',[(1,1),(2,2)])
db.executemany('INSERT INTO receipts VALUES (?,?)',[(str(i),json.dumps(dict(owner=i%2+1,dungeon_clear=[34350,1])))for i in range(100)])
expr="COALESCE(json_extract(j,'$.owner'),1001)";field="json_extract(j,'$.dungeon_clear[0]')";predicate="json_type(j,'$.dungeon_clear')='array'"
db.execute('CREATE INDEX ri ON receipts('+expr+','+field+')WHERE '+predicate);plans={}
for name,clause in [('parameter',expr+'=?'),('in',expr+' IN(SELECT uid FROM owners WHERE account=?)'),('unary',expr+' IN(SELECT +uid FROM owners WHERE account=?)')]:
    plans[name]=[r[-1]for r in db.execute('EXPLAIN QUERY PLAN SELECT '+field+',COUNT(*)FROM receipts WHERE '+clause+' AND '+predicate+' GROUP BY '+field,(1,))]
db.execute('DROP INDEX ri');expr='CAST('+expr+' AS INTEGER)';db.execute('CREATE INDEX ri ON receipts('+expr+','+field+')WHERE '+predicate)
plans['cast']=[r[-1]for r in db.execute('EXPLAIN QUERY PLAN SELECT '+field+',COUNT(*)FROM receipts WHERE '+expr+' IN(SELECT uid FROM owners WHERE account=?)AND '+predicate+' GROUP BY '+field,(1,))]
p=F/'query-affinity-probe.json';assert not p.exists();p.write_text(json.dumps(dict(sqlite_version=sqlite3.sqlite_version,plans=plans),indent=2)+'\n')
print(json.dumps(plans));db.close()
