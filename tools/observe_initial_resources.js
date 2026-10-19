// Read-only startup resource loader evidence; no status or control-flow changes.
const irM=Process.getModuleByName('x2_dx11.exe');
function irString(p){try{const n=p.add(16).readU64().toNumber();if(n>2048)return '<oversize>';return (p.add(24).readU64().toNumber()>7?p.readPointer():p).readUtf16String(n);}catch(e){return String(e);}}
const irPrefixes={"3545680": "48895c240848896c2410488974241848", "19066352": "40555356574154415541564157488d6c"};
let irAttempts=0;
const irTimer=setInterval(()=>{
 if(++irAttempts>1200){clearInterval(irTimer);send({event:'initial_resource_observer_timeout'});return;}
 if(!Object.entries(irPrefixes).every(([r,h])=>Array.from(new Uint8Array(irM.base.add(+r).readByteArray(16)),x=>x.toString(16).padStart(2,'0')).join('')===h))return;
 clearInterval(irTimer);
Interceptor.attach(irM.base.add(0x361a50),{onEnter(a){this.path=irString(a[1]);this.mode=a[3].toUInt32();},onLeave(r){send({event:'initial_resource_result',timestamp:Date.now(),path:this.path,mode:this.mode,flags:r.toUInt32()});}});
Interceptor.attach(irM.base.add(0x122edf0),{onEnter(a){try{send({event:'internal_game_dialog',timestamp:Date.now(),text:a[1].readUtf16String(),caller:this.returnAddress.toString()});}catch(e){}}});
send({event:'initial_resource_observer_ready',timestamp:Date.now()});

},25);
