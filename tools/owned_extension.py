"""Reload diagnostic scripts without retaining destroyed Frida handles."""
class OwnedExtension:
    def __init__(self,session,receive,report):
        self.session=session;self.receive=receive;self.report=report;self.script=None

    def load(self,source):
        # Compile first. A syntax error must leave the current observer alive.
        candidate=self.session.create_script(source)
        candidate.on('message',self.receive)
        previous,self.script=self.script,None
        if previous is not None:
            try:previous.unload()
            except Exception as exc:self.report('extension_unload_error',str(exc))
        try:candidate.load()
        except Exception:
            try:candidate.unload()
            except Exception:pass
            raise
        self.script=candidate
