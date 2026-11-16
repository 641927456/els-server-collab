// Native file reads, digest computation and comparisons remain authoritative.
// Fixed SHA256-verified resources use their independently witnessed digest.
// Native disk reads, hashing and result remain unchanged. No return is forced.
const riM=Process.getModuleByName('x2_dx11.exe'),riSpec=__INTEGRITY_SPEC__,riPrefixes=__INTEGRITY_PREFIXES__;
const riPinnedProfile=__PINNED_PROFILE__;
const riActive=new Map(),riPassed=new Set();let riAttempts=0;
const riHex=(p,n)=>Array.from(new Uint8Array(p.readByteArray(n)),v=>v.toString(16).padStart(2,'0')).join('');
function riStr(p){const n=p.add(16).readU64().toNumber();if(n>128)throw Error('Archive string size');return(p.add(24).readU64().toNumber()>15?p.readPointer():p).readUtf8String(n);}
function riEncode(s){return Array.from(s,(c,i)=>String.fromCharCode(c.charCodeAt(0)+(i===5?7:i===10?15:21))).join('');}
const riTimer=setInterval(()=>{
 if(++riAttempts>1200){clearInterval(riTimer);send({event:'resource_compat_unavailable'});return;}
 if(!Object.entries(riPrefixes).every(([r,h])=>riHex(riM.base.add(Number(r)),16)===h))return;
 clearInterval(riTimer);
 Interceptor.attach(riM.base.add(0x80e9b0),{
  onEnter(a){this.item=riActive.get(Process.getCurrentThreadId());this.out=a[1];},
  onLeave(){if(this.item)this.item.actual=this.out.readUtf8String(40);}
 });
 Interceptor.attach(riM.base.add(0x76d750),{
  onEnter(a){
   const pair=a[1],file=riStr(pair),expected=riStr(pair.add(32));
   this.item={file,expected_encoded:expected,adjusted:false,actual:null};riActive.set(Process.getCurrentThreadId(),this.item);
   const row=(riPinnedProfile?riSpec.entries:riSpec.compatibility).find(x=>x.file===file);
   if(!row)return;
   if(expected.length!==40||(!riPinnedProfile&&expected!==riEncode(row.original_digest))||pair.add(56).readU64().toNumber()<40){send({event:'resource_compat_refused',file,expected});return;}
   if(expected===riEncode(row.local_digest))return;
   pair.add(32).readPointer().writeUtf8String(riEncode(row.local_digest));this.item.adjusted=true;
   send({event:'resource_expected_compatibility',file,sha256:row.sha256,original_digest:row.original_digest,local_digest:row.local_digest,native_check_preserved:true,archive_modified:false,pinned_profile:riPinnedProfile,source:riPinnedProfile?'fixed-SHA256-and-witnessed-native-digest':'original-compatible-manifest'});
  },
  onLeave(r){
   const item=this.item;if(!item)return;riActive.delete(Process.getCurrentThreadId());
   const expected=riSpec.entries.find(x=>x.file===item.file);
   const ok=(r.toInt32()&255)===1,independent_match=!!expected&&item.actual===expected.local_digest;
   if(ok&&independent_match)riPassed.add(item.file);
   send({event:'native_archive_integrity_result',timestamp:Date.now(),...item,ok,independent_match,passed_count:riPassed.size});
   if(riPassed.size===riSpec.entries.length)send({event:'native_archive_integrity_sweep_passed',timestamp:Date.now(),count:riPassed.size,native_results:true,independent_digests:true});
  }
 });
 send({event:'resource_compat_ready',count:riSpec.entries.length,pinned:(riPinnedProfile?riSpec.entries:riSpec.compatibility).map(x=>x.file),pinned_profile:riPinnedProfile,native_check_preserved:true});
},25);

// CN labels in the original STX text draw. The draw copies its input
// synchronously, so the translated strings never enter widget or save state.
if (riPinnedProfile) {
  (() => {
    const entry = riM.base.add(0x490420);
    const caller = riM.base.add(0x5452e2);
    const entryPrefix = '4d85c90f8438040000488bc44c8940184889501055534155';
    const callerBytes = 'ff959000000090498bcee825d4';
    const texts = new Map([
      ['상의 옵션 보관함', '上衣效果保管箱'],
      ['빈슬롯', '空槽位'],
      ['每个服务器每天只能创建4个角色。', '每个服务器每天只能创建8个角色。'],
      ['每天最多只能创建4次。', '每天最多只能创建8次。'],
      ['角色每天只能创建4次。', '角色每天只能创建8次。'],
      ['已删除角色。\r\n每天最多只能创建4次。', '已删除角色。\r\n每天最多只能创建8次。'],
      ['完全删除角色。\r\n最终删除的角色将无法复原。\r\n角色每天只能创建4次。',
       '完全删除角色。\r\n最终删除的角色将无法复原。\r\n角色每天只能创建8次。'],
      ['中文6个字，英文12个字母。（不能使用特殊字符、空格）\r\n每个服务器每天只能创建4个角色。\r\n角色创建后3天内无法删除。',
       '中文6个字，英文12个字母。（不能使用特殊字符、空格）\r\n每个服务器每天只能创建8个角色。\r\n角色创建后3天内无法删除。'],
    ].map(([original, translated]) => [original, {
      original, translated: Memory.allocUtf16String(translated),
    }]));
    const initials = new Set(Array.from(texts.keys(), text => text.charCodeAt(0)));
    const observed = new Set();
    let attempts = 0;
    const timer = setInterval(() => {
      if (++attempts > 1200) {
        clearInterval(timer);
        send({event: 'tenebros_storage_text_entry_unavailable'});
        return;
      }
      if (riHex(entry, entryPrefix.length / 2) !== entryPrefix ||
          riHex(caller.sub(6), callerBytes.length / 2) !== callerBytes) return;
      clearInterval(timer);
      Interceptor.attach(entry, {
        onEnter(args) {
          if (!this.returnAddress.equals(caller) || args[3].isNull()) return;
          const input = args[3];
          const first = input.readU16();
          if (!initials.has(first)) return;
          const text = texts.get(input.readUtf16String());
          if (text === undefined) return;
          args[3] = text.translated;
          if (!observed.has(text.original)) {
            observed.add(text.original);
            if (first === 0xbe48 || first === 0xc0c1) {
              send({event: 'tenebros_storage_text_rendered', field: first === 0xbe48 ? 'empty_slot' : 'upper_title'});
            } else {
              send({event: 'character_creation_limit_text_rendered', daily_limit: 8});
            }
          }
        },
      });
    }, 25);
  })();
}
