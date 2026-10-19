const liM=Process.getModuleByName('x2_dx11.exe'),liSpecs=__INDEX_SPECS__;
const liHex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),x=>x.toString(16).padStart(2,'0')).join('');
function liString(p){const n=p.add(16).readU64().toNumber();if(n>512)return '';return(p.add(24).readU64().toNumber()>7?p.readPointer():p).readUtf16String(n);}
let liAttempts=0;
const liTimer=setInterval(()=>{
 if(++liAttempts>1200){clearInterval(liTimer);send({event:'local_resource_index_timeout'});return;}
 if(liHex(liM.base.add(0x3653b0),16)!=='__INDEX_PREFIX__')return;
 clearInterval(liTimer);
 Interceptor.attach(liM.base.add(0x3653b0),{onEnter(a){
  this.name=liString(a[0].add(0x60));const spec=liSpecs[this.name];if(!spec)return;
  const actual=liHex(a[2],72),count=a[3].add(8).readPointer().sub(a[3].readPointer()).toInt32()/64;
  const before=[0x20,0x28,0x2c,0x30].map(o=>a[4].add(o).readU32());
  if(actual!==spec.header||count!==spec.count){send({event:'local_resource_index_refused',name:this.name,actual,count,expected:spec,before});return;}
  this.copy=Memory.alloc(64);this.copy.writeByteArray(a[4].readByteArray(64));
  for(const [o,value] of [[0x20,spec.adler],[0x28,spec.time_sum],[0x2c,spec.size],[0x30,spec.count]])this.copy.add(o).writeU32(value);
  a[4]=this.copy;
  send({event:'local_resource_index_selected',timestamp:Date.now(),name:this.name,before,sha256:spec.sha256,entries:count,native_disk_parser:true,archive_modified:false});
 },onLeave(r){if(this.copy)send({event:'local_resource_index_result',timestamp:Date.now(),name:this.name,result:r.toUInt32()});}});
 send({event:'local_resource_index_compat_ready',timestamp:Date.now()});
},25);
