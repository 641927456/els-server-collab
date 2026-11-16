// Inline Armageddon lifetime input only. RSI and XMM0 are native live inputs.
function buildElsDungeonArmStub(site,resume,holdArm,originalBlock){
 const stub=Memory.alloc(Process.pageSize,{near:site,maxDistance:0x7fffffff});
 const w=new X86Writer(stub);
 // Windows x64 body stack is 16-byte aligned. Seven volatile GPRs plus 0x88
 // bytes preserve alignment, 32-byte call shadow space, and all volatile XMMs.
 w.putBytes([0x50,0x51,0x52,0x41,0x50,0x41,0x51,0x41,0x52,0x41,0x53,
             0x48,0x81,0xec,0x88,0,0,0]);
 for(let i=0;i<6;i++)w.putBytes([0xf3,0x0f,0x7f,0x44+i*8,0x24,0x20+i*16]);
 w.putBytes([0x48,0x89,0xf1]); // RCX=RSI (Actor); no lasting pointer retained.
 w.putCallAddress(holdArm);
 w.putBytes([0x85,0xc0]); // Hold predicate flags survive MOV/LEA/POP below.
 for(let i=0;i<6;i++)w.putBytes([0xf3,0x0f,0x6f,0x44+i*8,0x24,0x20+i*16]);
 w.putBytes([0x48,0x8d,0xa4,0x24,0x88,0,0,0,0x41,0x5b,0x41,0x5a,
             0x41,0x59,0x41,0x58,0x5a,0x59,0x58,0x75,0x08]);
 // True skips only original SUBSS. Original MOVSS, compare, cleanup continue.
 w.putBytes(originalBlock);w.putJmpAddress(resume);w.flush();
 if(!Memory.protect(stub,Process.pageSize,'r-x'))throw Error('Arm lifetime stub protection');
 return stub;
}
