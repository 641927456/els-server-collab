"""Bundle server code, pinned definitions and only runtime-read evidence files."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runtime-zip',type=Path,required=True)
    parser.add_argument('--wheel',type=Path,required=True)
    args=parser.parse_args(argv)
    target=args.output.resolve()
    if target.exists():raise ValueError('Bundle directory already exists')
    if hashlib.sha256(args.runtime_zip.read_bytes()).hexdigest()!='97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297':raise ValueError('Unverified official Python 3.13.16 runtime')
    observed=set()
    def opened(event,values):
        if event!='open' or not isinstance(values[0],(str,bytes)):return
        try:path=Path(values[0]).resolve()
        except (OSError,ValueError,TypeError):return
        if path.is_relative_to(ROOT/'analysis') and path.suffix in ('.json','.c','.lua'):
            observed.add(path)
    sys.addaudithook(opened)
    async def inspect():
        from els_server.application import Application
        from els_server.config import ServerConfig
        with tempfile.TemporaryDirectory() as temporary:
            app=Application(ServerConfig(state_file=Path(temporary)/'probe.sqlite3'))
            try:
                await app.start()
                def business():
                    # Initial equipment and deferred codecs have additional
                    # pinned witnesses beyond startup/character-list loading.
                    for unit in range(1,16):app.account.characters.create('Bundle'+str(unit),unit,'bundle-probe:'+str(unit))
                    app.account.character_list()
                    from els_server.protocol.local_messages import character_list
                    character_list('dx11_260923',characters=app.account.character_list())
                    from els_server.storage.shop_state import catalog,home_lists
                    for unit in range(1,16):catalog(unit);home_lists(unit)
                    from els_server.domain.dungeon_population import substage
                    for stage in range(3):substage(stage,True)
                    # Admission is deferred until 382. Its member codec reads
                    # a separate pinned fixture, not a startup dependency.
                    from els_server.protocol.dungeon_messages import dungeon_start
                    dungeon_start()
                    from els_server.domain.dungeon_routes import route_catalog,DungeonRun
                    import uuid
                    for identity in route_catalog()._data['routes']:DungeonRun(int(identity),str(uuid.uuid4()))
                    from els_server.domain.dungeon_clear import prototype_clear_notice,reward_clear_notice
                    prototype_clear_notice();prototype_clear_notice(True);reward_clear_notice(1,1)
                    from els_server.domain.drop_pickup import native_modes
                    native_modes()
                    # These catalogs are first read by deferred item/NPC
                    # actions, so startup alone does not reveal their files.
                    from els_server.domain.companions import catalog as companions
                    from els_server.domain.pet_support import catalog as pet_support
                    from els_server.domain.pet_accessory_rules import rules as pet_accessories
                    from els_server.domain.pet_progression import catalog as pet_progression
                    from els_server.domain.decomposition_rules import reward_definition
                    from els_server.domain.npc_trade import stock
                    from els_server.domain.mount_rules import catalog as mount_rules
                    mount_rules()
                    companions();pet_support();pet_accessories();pet_progression();reward_definition();stock()
                await app.call(business)
            finally:app.close()
    asyncio.run(inspect())
    files=set()
    for path in (ROOT/'els_server').rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix in ('.py','.json','.sqlite3'):files.add(path)
    files.update((ROOT/'config').glob('*.json'))
    files.update(observed)
    # Data manifests refer to native proof/source files used by deferred actions
    # such as repair, enhancement and skill unlocks. Follow only actual local
    # evidence paths, excluding saves, traces, logs and memory images.
    pending=[p for p in files if p.suffix=='.json'];visited=set()
    while pending:
        source=pending.pop()
        if source in visited:continue
        visited.add(source)
        def references(value):
            if isinstance(value,dict):
                for entry in value.values():references(entry)
            elif isinstance(value,list):
                for entry in value:references(entry)
            elif isinstance(value,str) and len(value)<260 and value.endswith(('.json','.c','.lua')) and '\n' not in value:
                for candidate in (source.parent/value,ROOT/value):
                    candidate=candidate.resolve()
                    if candidate.is_relative_to(ROOT/'analysis') and candidate.is_file() and candidate not in files:
                        files.add(candidate)
                        if candidate.suffix=='.json':pending.append(candidate)
        references(json.loads(source.read_text(encoding='utf8')))
    files.update(ROOT/p for p in ('config/friends-server.toml','requirements-server.txt','tools/create_friends_certificate.py','tools/install_friends_server.ps1','tools/backup_friends_server.py','tools/import_friends_save.py','tests/test_friends_server.py'))
    # Runtime provenance stays available without bundling any player saves,
    # network traces, memory snapshots, private keys or account credentials.
    manifest=[];target.mkdir(parents=True)
    for source in sorted(files):
        relative=source.relative_to(ROOT)
        destination=target/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        content=source.read_bytes();destination.write_bytes(content)
        manifest.append(dict(path=relative.as_posix(),size=len(content),sha256=hashlib.sha256(content).hexdigest()))
    def unpack(source,folder):
        with zipfile.ZipFile(source) as archive:
            if any(not (folder/p.filename).resolve().is_relative_to(folder.resolve()) for p in archive.infolist()):raise ValueError('Unsafe archive path')
            archive.extractall(folder)
    unpack(args.runtime_zip,target/'python')
    unpack(args.wheel,target/'vendor')
    (target/'python/python313._pth').write_text('python313.zip\n.\n..\n../vendor\nimport site\n',encoding='ascii')
    (target/'bundle-manifest.json').write_text(json.dumps(dict(schema_version=1,files=manifest,runtime_sha256=hashlib.sha256(args.runtime_zip.read_bytes()).hexdigest(),wheel_sha256=hashlib.sha256(args.wheel.read_bytes()).hexdigest()),indent=2),encoding='utf8')
    archive=target.with_suffix('.zip')
    if archive.exists():raise ValueError('Bundle archive already exists')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as out:
        for path in target.rglob('*'):
            if path.is_file():out.write(path,path.relative_to(target))
    print(json.dumps(dict(directory=str(target),archive=str(archive),files=len(manifest),bytes=archive.stat().st_size,sha256=hashlib.sha256(archive.read_bytes()).hexdigest())))


if __name__=='__main__':main()
