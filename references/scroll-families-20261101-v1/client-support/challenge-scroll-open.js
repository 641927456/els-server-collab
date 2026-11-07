/* Pinned dx11_260923, EXE SHA256
 * 6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709.
 * Human rule 2026-11-01: both challenge categories always open.
 * The inventory's eight-ID switch has already classified the scroll and
 * populated EBX=4/5. Only its single-week comparison is adjusted. All original
 * eligibility, confirmation, packet writers and server transactions remain.
 */
function installChallengeScrollSupport(base) {
  const key = '__elsChallengeScrollOpenV1';
  if (globalThis[key]) return globalThis[key];
  function equal(offset, hex) {
    const expected=hex.match(/../g).map(s=>parseInt(s,16));
    const actual=new Uint8Array(base.add(offset).readByteArray(expected.length));
    if (!expected.every((v,i)=>v===actual[i])) throw Error('Challenge scroll native byte guard');
  }
  equal(0x2378760,'488b0509f749028b8040100000c3');
  equal(0x22262ee,'e86d2415003bc30f84d4010000');
  const hook=Interceptor.attach(base.add(0x22262f3),{
    onEnter() {
      const category=this.context.rbx.toInt32();
      if (category===4 || category===5) this.context.rax=this.context.rbx;
    }
  });
  const state={detach(){hook.detach();delete globalThis[key];}};
  globalThis[key]=state;return state;
}
// BEGIN production bootstrap
const client=Process.enumerateModules().find(m=>/^x2\.exe$/i.test(m.name));
if (!client) throw Error('Pinned X2 module required');
installChallengeScrollSupport(client.base);
