"""User-authorized friends reproduction of the existing selected pair.

Uses the already pinned local calendar and consumers. Initial activation has
one durable settings receipt; later administrator switches survive restarts.
No new UI, client timer, growth enrollment or reward formula is introduced.
"""
from pathlib import Path
import hashlib

PACK_SHA256='36e60b584d2af90dced5bcd0bc3ed85d27bcfd0688ace5c1649ba44364160c0e'
INITIAL_OPERATION='46514b9a-d25e-5db6-b24f-b0a241a19701'

def install(app):
    if app.config.mode!='friends' or app.config.profile!='integrated_dx11' or app.activity2026_awards_factory is not None:return
    from els_server.domain.selected_2026_pair_runtime import from_pack
    pack=Path(__file__).resolve().parents[1]/'data/selected2026/local-pair.json'
    if hashlib.sha256(pack.read_bytes()).hexdigest()!=PACK_SHA256:raise ValueError('Authorized reproduction calendar changed')
    manager=from_pack(app.config.state_file,pack);manager.attach(app);manager.install()
    if manager.state['revision']==0:
        manager.update(dict(operation_id=INITIAL_OPERATION,expected_revision=0,
            reason='User authorized existing local reproduction calendar for friends attendance and online title',
            enabled=dict(growth=False,attendance=True,online=True)))
    app.activity2026_awards_factory=manager
