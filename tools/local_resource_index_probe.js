// 只观察、不修改：记录每个资源包「磁盘 72 字节头」与「客户端内嵌目录描述符」
// 的差异，用来定位到底哪些档案的索引发生了漂移。完全不写客户端内存。
const liM = Process.getModuleByName('x2_dx11.exe');
const liHex = (p, n) => Array.from(new Uint8Array(p.readByteArray(n)), x => x.toString(16).padStart(2, '0')).join('');
function liString(p) { const n = p.add(16).readU64().toNumber(); if (n > 512) return ''; return (p.add(24).readU64().toNumber() > 7 ? p.readPointer() : p).readUtf16String(n); }
let liAttempts = 0;
const liTimer = setInterval(() => {
  if (++liAttempts > 1200) { clearInterval(liTimer); send({ event: 'local_resource_index_timeout' }); return; }
  if (liHex(liM.base.add(0x3653b0), 16) !== '__INDEX_PREFIX__') return;
  clearInterval(liTimer);
  Interceptor.attach(liM.base.add(0x3653b0), {
    onEnter(a) {
      try {
        const name = liString(a[0].add(0x60));
        const bytes = new Uint8Array(a[2].readByteArray(72));
        const dv = new DataView(bytes.buffer);
        const disk = { count: dv.getUint32(52, true), time_sum: dv.getUint32(60, true), adler: dv.getUint32(64, true), size: dv.getUint32(68, true) };
        const desk = { adler: a[4].add(0x20).readU32(), time_sum: a[4].add(0x28).readU32(), size: a[4].add(0x2c).readU32(), count: a[4].add(0x30).readU32() };
        const live = a[3].add(8).readPointer().sub(a[3].readPointer()).toInt32() / 64;
        const same = disk.count === desk.count && disk.time_sum === desk.time_sum && disk.adler === desk.adler && disk.size === desk.size;
        send({ event: 'local_resource_index_observe', name: name, same: same, disk: disk, descriptor: desk, live_count: live, header: liHex(a[2], 72) });
      } catch (e) {
        send({ event: 'local_resource_index_observe_error', error: String(e) });
      }
    }
  });
  send({ event: 'local_resource_index_probe_ready', timestamp: Date.now() });
}, 25);
