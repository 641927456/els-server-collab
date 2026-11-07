from pathlib import Path
H=Path(__file__).resolve().parent
source=(H/'verify_persistent_native_cycle.py').read_text('utf8')
source=source.replace("        counts=dict(namespace['counts'])","        counts=dict(namespace['counts']);checkpoint=c.app.checkpoints.snapshot();assert checkpoint['background_thread_priority']is not None and checkpoint['background_thread_priority']<0 and checkpoint['prewarmed']and checkpoint['runs']>1")
source=source.replace('persistent-native-cycle-tests.json','background-checkpoint-persistent-tests.json').replace('currency_and_ACK_exact=True,','currency_and_ACK_exact=True,background_checkpoint=checkpoint,background_thread_joined=not c.app.checkpoints.thread.is_alive(),')
exec(compile(source,str(H/'verify_persistent_native_cycle.py'),'exec'),globals())
