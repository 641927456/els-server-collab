"""Allow only existing achievement indexes to be prepared before listeners."""
import ast
WARM="""from contextlib import closing
import sqlite3
from els_server.storage.achievement_history import ensure_indexes as prepare_achievement_indexes
from els_server.storage.sqlite_timing import write_transaction
with closing(sqlite3.connect(self.config.state_file,timeout=10))as db,write_transaction(db):
    prepare_achievement_indexes(db)"""
def normalize_startup_index(tree):
 app=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='Application')
 start=next(n for n in app.body if isinstance(n,ast.AsyncFunctionDef)and n.name=='start')
 init=next(n for n in start.body if isinstance(n,ast.FunctionDef)and n.name=='initialize')
 pos=next(i for i,n in enumerate(init.body)if isinstance(n,ast.Expr)and ast.unparse(n)=='prepare(self.config.state_file)')+1
 expected=ast.parse(WARM).body
 assert [ast.dump(n)for n in init.body[pos:pos+len(expected)]]==[ast.dump(n)for n in expected]
 del init.body[pos:pos+len(expected)]
 return tree
