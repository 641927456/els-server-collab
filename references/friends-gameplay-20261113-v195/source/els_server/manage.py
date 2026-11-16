"""Offline account administration; never prints or copies a game save."""
import argparse
import hashlib
import json
from pathlib import Path
import ssl
from els_server.config import ServerConfig
from els_server.storage.accounts import Accounts


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    sub=parser.add_subparsers(dest='action',required=True)
    create=sub.add_parser('create');create.add_argument('name');create.add_argument('--host',required=True);create.add_argument('--output',type=Path,required=True)
    sub.add_parser('list')
    disable=sub.add_parser('disable');disable.add_argument('name')
    audit=sub.add_parser('anti-cheat',help='Read recent server-side cheat review signals')
    audit.add_argument('--account-id',type=int)
    audit.add_argument('--run-id')
    audit.add_argument('--limit',type=int,default=50)
    audit.add_argument('--log-dir',type=Path,help='Match the server startup log directory override')
    args=parser.parse_args(argv);config=ServerConfig.load(args.config)
    if args.action=='anti-cheat':
        if not 1 <= args.limit <= 1000 or args.account_id is not None and args.account_id < 1:
            audit.error('Expected a limit of 1–1000 and a positive account ID')
        from els_server.anti_cheat import recent_signals
        for row in recent_signals(args.log_dir or config.log_dir,config.log_backups,
                account_id=args.account_id,run_id=args.run_id,limit=args.limit):
            print(json.dumps(row))
        return 0
    if config.mode!='friends':parser.error('Requires friends configuration')
    registry=Accounts(config.accounts_file)
    if args.action=='create':
        from els_server.friends_bridge import BridgeConfig
        fingerprint=hashlib.sha256(ssl.PEM_cert_to_DER_cert(config.tls_cert.read_text(encoding='ascii'))).hexdigest()
        # Validate destination and writeability before creating a credential.
        BridgeConfig(args.host,config.port,args.name,'x'*43,fingerprint,probe_port=config.client_probe_port)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf8') as output:
            account=registry.create(args.name)
            json.dump(dict(host=args.host,port=config.port,name=args.name,token=account['token'],certificate_sha256=fingerprint,probe_port=config.client_probe_port),output,indent=2)
        print(json.dumps(dict(id=account['id'],name=args.name,client_config=str(args.output.resolve()))))
    elif args.action=='list':print(json.dumps(registry.list()))
    elif args.action=='disable':registry.disable(args.name);print('Account disabled')
    return 0


if __name__=='__main__':raise SystemExit(main())
