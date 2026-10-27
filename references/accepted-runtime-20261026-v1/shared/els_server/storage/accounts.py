"""Owner-issued random access tokens; the registry never stores their plaintext."""
from contextlib import closing
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from pathlib import Path


class Accounts:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(self.connect()) as db,db:
            db.execute('CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY CHECK(id>=2), name TEXT NOT NULL UNIQUE, token_hash TEXT NOT NULL, enabled INTEGER NOT NULL CHECK(enabled IN (0,1)))')
            db.execute('CREATE TABLE IF NOT EXISTS account_passwords (account_id INTEGER PRIMARY KEY REFERENCES accounts(id), salt BLOB NOT NULL, digest BLOB NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS account_sessions (token_hash TEXT PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id), expires INTEGER NOT NULL, created INTEGER NOT NULL)')

    def connect(self):return sqlite3.connect(self.path,timeout=10)

    def create(self,name):
        if not isinstance(name,str) or not re.fullmatch(r'[a-z][a-z0-9_]{2,23}',name):raise ValueError('Account name: 3-24 lowercase ASCII letters, digits or underscores')
        token=secrets.token_urlsafe(32)
        with closing(self.connect()) as db,db:
            db.execute('BEGIN IMMEDIATE')
            identity=db.execute('SELECT COALESCE(MAX(id),1)+1 FROM accounts').fetchone()[0]
            db.execute('INSERT INTO accounts VALUES (?,?,?,1)',(identity,name,hashlib.sha256(token.encode()).hexdigest()))
        return dict(id=identity,name=name,token=token)

    def authenticate(self,name,token):
        if not isinstance(name,str) or not isinstance(token,str) or not 32<=len(token)<=128:raise ValueError('Authentication failed')
        with closing(self.connect()) as db:
            row=db.execute('SELECT id,name,token_hash,enabled FROM accounts WHERE name=?',(name,)).fetchone()
        supplied=hashlib.sha256(token.encode()).hexdigest()
        match=hmac.compare_digest(supplied,row[2] if row else '0'*64)
        if not match:
            with closing(self.connect()) as db:
                session=db.execute('SELECT account_id FROM account_sessions WHERE token_hash=? AND expires>?',(supplied,int(time.time()))).fetchone()
            match=bool(row and session and session[0]==row[0])
        if not row or not match or row[3]!=1:raise ValueError('Authentication failed')
        return dict(id=row[0],name=row[1])

    @staticmethod
    def password_bytes(password):
        if (not isinstance(password,str) or not 8<=len(password)<=64
            or len(password.encode('utf8'))>128 or any(ord(c)<32 or ord(c)==127 for c in password)):
            raise ValueError('invalid_password')
        return password.encode('utf8')

    @staticmethod
    def password_digest(raw,salt):return hashlib.scrypt(raw,salt=salt,n=16384,r=8,p=1,maxmem=64*1024*1024,dklen=32)

    def register(self,name,password,capacity=64):
        if not isinstance(name,str) or not re.fullmatch(r'[a-z][a-z0-9_]{2,23}',name):raise ValueError('invalid_name')
        salt=secrets.token_bytes(16);digest=self.password_digest(self.password_bytes(password),salt)
        try:
            with closing(self.connect()) as db,db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute('SELECT 1 FROM accounts WHERE name=?',(name,)).fetchone():raise ValueError('name_taken')
                if db.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]>=capacity:raise ValueError('registration_full')
                identity=db.execute('SELECT COALESCE(MAX(id),1)+1 FROM accounts').fetchone()[0]
                db.execute('INSERT INTO accounts VALUES (?,?,?,1)',(identity,name,hashlib.sha256(secrets.token_bytes(32)).hexdigest()))
                db.execute('INSERT INTO account_passwords VALUES (?,?,?)',(identity,salt,digest))
                return self.issue_session(db,identity,name)
        except sqlite3.IntegrityError:raise ValueError('name_taken') from None

    def password_login(self,name,password):
        raw=self.password_bytes(password)
        if not isinstance(name,str) or not re.fullmatch(r'[a-z][a-z0-9_]{2,23}',name):raise ValueError('bad_credentials')
        with closing(self.connect()) as db,db:
            row=db.execute('SELECT a.id,a.name,a.enabled,p.salt,p.digest FROM accounts a LEFT JOIN account_passwords p ON a.id=p.account_id WHERE a.name=?',(name,)).fetchone()
            supplied=self.password_digest(raw,row[3] if row and row[3] else bytes(16))
            if not row or row[2]!=1 or row[4] is None or not hmac.compare_digest(supplied,row[4]):raise ValueError('bad_credentials')
            return self.issue_session(db,row[0],row[1])

    def issue_session(self,db,identity,name):
        token=secrets.token_urlsafe(32);now=int(time.time());expires=now+30*86400
        db.execute('DELETE FROM account_sessions WHERE expires<=?',(now,))
        db.execute('INSERT INTO account_sessions VALUES (?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),identity,expires,now))
        db.execute('DELETE FROM account_sessions WHERE account_id=? AND token_hash NOT IN (SELECT token_hash FROM account_sessions WHERE account_id=? ORDER BY created DESC,rowid DESC LIMIT 8)',(identity,identity))
        return dict(account_id=identity,name=name,token=token,expires=expires)

    def list(self):
        with closing(self.connect()) as db:
            return [dict(id=r[0],name=r[1],enabled=bool(r[2])) for r in db.execute('SELECT id,name,enabled FROM accounts ORDER BY id')]

    def enabled(self,identity):
        with closing(self.connect()) as db:return db.execute('SELECT enabled FROM accounts WHERE id=?',(identity,)).fetchone()==(1,)

    def disable(self,name):
        with closing(self.connect()) as db,db:
            if db.execute('UPDATE accounts SET enabled=0 WHERE name=?',(name,)).rowcount!=1:raise ValueError('Unknown account')
