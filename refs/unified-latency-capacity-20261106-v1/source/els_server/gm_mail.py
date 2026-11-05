"""Local GM mail administration. Reviewed account IDs, SQLite backups, idempotence."""
import argparse
from contextlib import closing
import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from els_server.config import ServerConfig
from els_server.storage.game_mail import gm_campaign


def backup(source,destination):
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src:
        with closing(sqlite3.connect(destination)) as dest:
            src.backup(dest)
            if dest.execute('PRAGMA quick_check').fetchone()!=('ok',):raise ValueError('Mail backup integrity')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True,help='Reviewed JSON: campaign,ed,title,body,recipients:[{id,name}]')
    p.add_argument('--apply',action='store_true')
    a=p.parse_args(argv);c=ServerConfig.load(a.config)
    if c.mode!='friends':raise ValueError('GM campaign requires friends configuration')
    raw=a.plan.read_bytes();plan=json.loads(raw)
    required={'campaign','ed','title','body','recipients'}
    if set(plan)!=required:raise ValueError('Mail plan fields')
    expected=plan['recipients']
    if not expected or any(set(r)!={'id','name'} for r in expected):raise ValueError('Reviewed recipients required')
    ids=[r['id'] for r in expected]
    with closing(sqlite3.connect(c.accounts_file.as_uri()+'?mode=ro',uri=True)) as db:
        actual={r[0]:(r[1],r[2]) for r in db.execute('SELECT id,name,enabled FROM accounts')}
    for r in expected:
        if actual.get(r['id'])!=(r['name'],1):raise ValueError('Account identity/enabled status changed')
    report=dict(applied=False,campaign=plan['campaign'],plan_sha256=hashlib.sha256(raw).hexdigest(),
                recipients=expected,ed_per_account=plan['ed'])
    if a.apply:
        # A dedicated maintenance lock serializes administration with releases.
        root=a.config.resolve().parent.parent
        lock=root/'run/release.lock'
        if (root/'run/server.stop').exists():raise ValueError('Release/stop in progress')
        with lock.open('x',encoding='ascii') as handle:
            handle.write(plan['campaign']);handle.flush()
            try:
                if (root/'run/server.stop').exists():raise ValueError('Stop started before GM lock')
                stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
                # Validate the campaign before using it in a backup path.
                import re
                if not isinstance(plan['campaign'],str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{2,95}',plan['campaign']):raise ValueError('Invalid campaign')
                folder=root/'backups/gm-mail'/plan['campaign']/stamp;folder.mkdir(parents=True,exist_ok=False)
                backup(c.state_file,folder/'game.sqlite3');backup(c.accounts_file,folder/'accounts.sqlite3')
                report['backup']=str(folder.resolve())
                result=gm_campaign(c.state_file,plan['campaign'],ids,ed=plan['ed'],title=plan['title'],body=plan['body'])
                report.update(applied=True,result=result)
                (folder/'receipt.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
            finally:
                # Windows requires the handle to be closed before unlinking.
                handle.close();lock.unlink()
    print(json.dumps(report,ensure_ascii=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
