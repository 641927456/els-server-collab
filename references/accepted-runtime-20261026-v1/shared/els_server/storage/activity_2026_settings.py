"""Durable switches for the selected three, independent of reward ledgers."""
import hashlib,json,sqlite3,time,uuid
from contextlib import closing

KEYS={'attendance','growth','online'}
def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'))
def flags(value):
    if type(value) is not dict or set(value)!=KEYS or any(type(v) is not bool for v in value.values()):
        raise ValueError('必须提供这三项活动的布尔开关')
    return dict(value)
def request(value):
    if type(value) is not dict or set(value)!={'operation_id','reason','expected_revision','enabled'}:
        raise ValueError('活动设置请求字段无效')
    try:
        if type(value['operation_id']) is not str or str(uuid.UUID(value['operation_id']))!=value['operation_id']:raise ValueError()
    except (ValueError,AttributeError):raise ValueError('操作编号无效') from None
    if type(value['reason']) is not str or not 2<=len(value['reason'].strip())<=200:raise ValueError('请输入2至200字的操作原因')
    if type(value['expected_revision']) is not int or not 0<=value['expected_revision']<2**63-1:raise ValueError('活动配置版本无效')
    return dict(value,enabled=flags(value['enabled']))

class Settings:
    def __init__(self,path,binding):
        self.path=path;self.binding=canonical(binding);self.digest=hashlib.sha256(self.binding.encode()).hexdigest()

    def initialize(self):
        with closing(sqlite3.connect(self.path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS selected2026_settings (id INTEGER PRIMARY KEY CHECK(id=1), binding_sha256 TEXT NOT NULL, binding_json TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>=0), enabled_json TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS selected2026_settings_operations (operation_id TEXT PRIMARY KEY, digest TEXT NOT NULL, request_json TEXT NOT NULL, previous_revision INTEGER NOT NULL, revision INTEGER NOT NULL, applied_at REAL NOT NULL)')
            old=db.execute('SELECT binding_sha256,binding_json FROM selected2026_settings WHERE id=1').fetchone()
            if old is not None and old!=(self.digest,self.binding):raise ValueError('已保存活动规则或周期不同，不能覆盖历史领奖身份')
            db.execute('INSERT OR IGNORE INTO selected2026_settings VALUES (1,?,?,0,?)',(self.digest,self.binding,canonical({k:False for k in KEYS})))

    def _snapshot(self,db):
        row=db.execute('SELECT binding_sha256,binding_json,revision,enabled_json FROM selected2026_settings WHERE id=1').fetchone()
        if row is None or row[:2]!=(self.digest,self.binding):raise ValueError('活动规则绑定已改变')
        return dict(revision=row[2],enabled=flags(json.loads(row[3])),binding_sha256=self.digest)

    def snapshot(self):
        with closing(sqlite3.connect(self.path,timeout=10)) as db:return self._snapshot(db)

    def _review(self,db,value):
        value=request(value);snapshot=self._snapshot(db)
        digest=hashlib.sha256(canonical(value).encode()).hexdigest()
        old=db.execute('SELECT digest,revision FROM selected2026_settings_operations WHERE operation_id=?',(value['operation_id'],)).fetchone()
        if old is not None:
            if old[0]!=digest:raise ValueError('同一操作编号不能改变内容')
            return dict(snapshot,operation_id=value['operation_id'],operation_revision=old[1],replayed=True)
        if snapshot['revision']!=value['expected_revision']:raise ValueError('活动配置已更新，请刷新后提交')
        return dict(snapshot,operation_id=value['operation_id'],operation_revision=snapshot['revision']+1,replayed=False)

    def review(self,value):
        with closing(sqlite3.connect(self.path,timeout=10)) as db:return self._review(db,value)

    def update(self,value):
        value=request(value)
        with closing(sqlite3.connect(self.path,timeout=10)) as db,db:
            db.execute('BEGIN IMMEDIATE');review=self._review(db,value)
            if review['replayed']:return review
            revision=review['operation_revision']
            db.execute('UPDATE selected2026_settings SET revision=?,enabled_json=? WHERE id=1',(revision,canonical(value['enabled'])))
            db.execute('INSERT INTO selected2026_settings_operations VALUES (?,?,?,?,?,?)',
                (value['operation_id'],hashlib.sha256(canonical(value).encode()).hexdigest(),canonical(value),value['expected_revision'],revision,time.time()))
            return dict(self._snapshot(db),operation_id=value['operation_id'],operation_revision=revision,replayed=False)
