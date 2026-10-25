// Run the actual Frida script against controlled pointers; never attach a client.
const fs = require('fs'), vm = require('vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
function trial({pinned=true, measured='B', expected='D', known=true}={}) {
  const file='data002.kom', original='A'.repeat(40), local='B'.repeat(40);
  const encode=s=>Array.from(s,(c,i)=>String.fromCharCode(c.charCodeAt(0)+(i===5?7:i===10?15:21))).join('');
  let expectedValue=encode(expected.repeat(40)), timer;
  const writes=[], events=[], hooks={};
  function ptr(offset=0) {
    return {add(n){return ptr(offset+n);},
      readU64(){return {toNumber(){return offset===16?file.length:offset===48?40:64;}};},
      readPointer(){return {readUtf8String(){return offset===0?file:expectedValue;},
        writeUtf8String(value){expectedValue=value;writes.push(value);}};},
      readUtf8String(){return offset===0?file:expectedValue;}};
  }
  const row={file,original_digest:original,local_digest:local,sha256:'fixed-fixture'};
  const spec={entries:known?[row]:[],compatibility:known?[row]:[]};
  const prefixes={};prefixes[0x76d750]='0'.repeat(32);prefixes[0x80e9b0]='0'.repeat(32);
  const base={add(address){return {address,readByteArray(n){return new Uint8Array(n).buffer;}};}};
  const context={Process:{getModuleByName(){return {base};},getCurrentThreadId(){return 1;}},
    Interceptor:{attach(p,h){hooks[p.address]=h;}},setInterval(fn){timer=fn;return 1;},
    clearInterval(){},send(e){events.push(e);},Uint8Array};
  vm.runInNewContext(source.replace('__INTEGRITY_SPEC__',JSON.stringify(spec))
    .replace('__INTEGRITY_PREFIXES__',JSON.stringify(prefixes))
    .replace('__PINNED_PROFILE__',pinned?'true':'false'),context);
  timer();
  const check={},digest={};
  hooks[0x76d750].onEnter.call(check,[null,ptr()]);
  hooks[0x80e9b0].onEnter.call(digest,[null,{readUtf8String(){return measured.repeat(40);}}]);
  hooks[0x80e9b0].onLeave.call(digest);
  const nativePass=expectedValue===encode(measured.repeat(40));
  hooks[0x76d750].onLeave.call(check,{toInt32(){return nativePass?1:0;}});
  const result=events.find(e=>e.event==='native_archive_integrity_result');
  return {nativePass,independentMatch:result.independent_match,writes,
    learnedMeasuredDigest:writes.includes(encode(measured.repeat(40))) && measured!=='B'};
}
console.log(JSON.stringify({
  fixed:trial(),tampered:trial({measured:'C'}),unknown:trial({known:false,measured:'C'}),
  legacyAccepted:trial({pinned:false,expected:'A'}),legacyUnknownExpected:trial({pinned:false,expected:'D'})
}));
