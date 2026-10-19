// Read-only evidence at the actual character-selection resource-error branch.
// Exact DX11 6c6b5180 prefixes from the unmodified runtime image.
const rdModule=Process.getModuleByName('x2_dx11.exe');
function rdFlags(){try{return rdModule.base.add(0x4817e80).readPointer().add(0xb64).readU32();}catch(e){return null;}}
function rdText(p){try{return p.isNull()?null:p.readUtf16String(512).split('\0')[0];}catch(e){return '<unreadable>';}}
const rdChecks={0x1384460:'48895c24185556574154415541564157',0x1384840:'8b88640b000049c7c4ffffffff85c90f',0x74ecd0:'48895c24185556574154415541564157'};
let rdAttempts=0,rdCount=0;
const rdTimer=setInterval(()=>{
 if(++rdAttempts>1200){clearInterval(rdTimer);send({event:'resource_dialog_observer_timeout'});return;}
 if(!Object.entries(rdChecks).every(([r,h])=>Array.from(new Uint8Array(rdModule.base.add(+r).readByteArray(16)),x=>x.toString(16).padStart(2,'0')).join('')===h))return;
 clearInterval(rdTimer);
 Interceptor.attach(rdModule.base.add(0x1384460),{onEnter(){if(rdCount++<200)send({event:'resource_character_entry',timestamp:Date.now(),flags:rdFlags()});}});
 Interceptor.attach(rdModule.base.add(0x1384840),function(){if(rdCount++<200)send({event:'resource_character_check',timestamp:Date.now(),flags:this.context.rax.add(0xb64).readU32()});});
 Interceptor.attach(rdModule.base.add(0x74ecd0),{onEnter(a){if(rdCount++<200)send({event:'resource_native_dialog',timestamp:Date.now(),text:rdText(a[3]),flags:rdFlags(),caller:this.returnAddress.sub(rdModule.base).toString()});}});
 send({event:'resource_dialog_observer_ready',timestamp:Date.now(),flags:rdFlags(),read_only:true});
},25);
