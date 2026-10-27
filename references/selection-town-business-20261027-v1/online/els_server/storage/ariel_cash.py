"""Account cash is a server-local ledger, initially zero; explicit GM credit only."""
from contextlib import closing,contextmanager
from pathlib import Path
import hashlib,json,sqlite3,time,uuid

MAX_CASH=2**31-1
TABLE='ariel_account_cash'
OPS='ariel_cash_operations'

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def account_id(value):
    if type(value)is not int or not 1<=value<2**63:raise ValueError('Cash account identity')
    return value
def operation(value):
    if not isinstance(value,str)or str(uuid.UUID(value))!=value or uuid.UUID(value).version!=4:
        raise ValueError('Cash operation must be an explicit UUID4')
    return value
def present(db,name):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())
def initialize(db):
    if not db.in_transaction:raise ValueError('Cash initialization requires transaction')
    db.execute('CREATE TABLE IF NOT EXISTS ariel_account_cash (account_id INTEGER PRIMARY KEY CHECK(account_id>=1),balance INTEGER NOT NULL CHECK(balance>=0 AND balance<=2147483647),revision INTEGER NOT NULL CHECK(revision>=1))')
    db.execute('CREATE TABLE IF NOT EXISTS ariel_cash_operations (operation_id TEXT PRIMARY KEY,account_id INTEGER NOT NULL,action TEXT NOT NULL,request_hash TEXT NOT NULL,receipt_json TEXT NOT NULL,created_at INTEGER NOT NULL)')
def balance(db,account):
    account_id(account)
    row=db.execute('SELECT balance,revision FROM ariel_account_cash WHERE account_id=?',(account,)).fetchone()if present(db,TABLE)else None
    if row is None:return dict(balance=0,revision=0)
    if any(type(x)is not int for x in row)or not 0<=row[0]<=MAX_CASH or not 1<=row[1]<2**63:raise ValueError('Stored cash boundary')
    return dict(balance=row[0],revision=row[1])
@contextmanager
def reading(path):
    path=Path(path)
    if not path.is_file():raise ValueError('Cash state file missing')
    with snapshot_connection(path)as db:
        db.execute('BEGIN');yield db
def snapshot(path,account,*,validate=lambda:None):
    validate()
    with reading(path)as db:
        result=balance(db,account);validate();return result
def credit_receipt(path,account,key,*,validate):
    account_id(account);operation(key);validate(account)
    with reading(path)as db:
        row=db.execute('SELECT account_id,action,receipt_json FROM ariel_cash_operations WHERE operation_id=?',(key,)).fetchone()if present(db,OPS)else None
        if row is None:validate(account);return dict(committed=False,receipt=None)
        if row[:2]!=(account,'gm-credit'):raise ValueError('Cash credit receipt account/action')
        result=json.loads(row[2]);validate(account);return dict(committed=True,receipt=result)
def previous(db,key,account,action,request_hash):
    row=db.execute('SELECT account_id,action,request_hash,receipt_json FROM ariel_cash_operations WHERE operation_id=?',(key,)).fetchone()if present(db,OPS)else None
    if row is None:return None
    if row[:3]!=(account,action,request_hash):raise ValueError('Cash conflicting retry')
    receipt=json.loads(row[3]);canonical(receipt)
    return receipt
def replace(db,account,expected,delta):
    if not db.in_transaction:raise ValueError('Cash mutation requires transaction')
    if type(delta)is not int or not -MAX_CASH<=delta<=MAX_CASH or delta==0:raise ValueError('Cash delta')
    current=balance(db,account)
    if current!=expected:raise ValueError('Cash concurrent revision')
    updated=current['balance']+delta
    if not 0<=updated<=MAX_CASH or current['revision']>=2**63-1:raise ValueError('Cash insufficient balance or overflow')
    initialize(db)
    if current['revision']==0:db.execute('INSERT INTO ariel_account_cash VALUES (?,?,1)',(account,updated))
    elif db.execute('UPDATE ariel_account_cash SET balance=?,revision=revision+1 WHERE account_id=? AND balance=? AND revision=?',(updated,account,current['balance'],current['revision'])).rowcount!=1:raise ValueError('Cash compare-and-swap')
    return dict(balance=updated,revision=current['revision']+1)
def record(db,key,account,action,request_hash,receipt,moment):
    if not db.in_transaction:raise ValueError('Cash receipt requires transaction')
    initialize(db)
    db.execute('INSERT INTO ariel_cash_operations VALUES (?,?,?,?,?,?)',(key,account,action,request_hash,canonical(receipt),moment))
def credit(path,value,*,validate,now=time.time):
    if not isinstance(value,dict)or set(value)!={'operation_id','account_id','amount','expected_balance','reason'}:raise ValueError('Cash GM credit fields')
    key=operation(value['operation_id']);account=account_id(value['account_id']);amount=value['amount'];expected=value['expected_balance'];reason=value['reason']
    if(type(amount)is not int or not 1<=amount<=MAX_CASH or type(expected)is not int or not 0<=expected<=MAX_CASH
       or not isinstance(reason,str)or not 1<=len(reason.strip())<=256):raise ValueError('Cash explicit GM credit boundary')
    hashed=digest(value);path=Path(path)
    if not path.is_file():raise ValueError('Cash state file missing')
    with closing(sqlite3.connect(path,timeout=10))as db:
        try:
            db.execute('BEGIN IMMEDIATE');validate(account)
            old=previous(db,key,account,'gm-credit',hashed)
            if old is not None:validate(account);db.commit();return old
            before=balance(db,account)
            if before['balance']!=expected:raise ValueError('Cash GM stale expected balance')
            after=replace(db,account,before,amount)
            moment=int(now())
            if not 0<=moment<2**40:raise ValueError('Cash clock')
            result=dict(operation_id=key,account_id=account,credited=amount,before=before,after=after,reason=reason,created_at=moment,server_local_funding=True,ED_delta=0)
            canonical(result);validate(account);record(db,key,account,'gm-credit',hashed,result,moment);db.commit();return result
        except BaseException:db.rollback();raise

from els_server.storage.read_scope import snapshot_connection
