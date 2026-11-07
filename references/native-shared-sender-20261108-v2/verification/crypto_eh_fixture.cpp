// Owned header-free MSVC fixture; no game or player files are loaded.
typedef unsigned int U32;
typedef U32 (*GetCounter)(void *);
typedef void (*IncrementCounter)(void *);
typedef void (*SleepFn)(U32);
typedef void (*QueueFn)(U32);
typedef U32 (*ErrorGet)();
typedef void (*ErrorSet)(U32);
static void *sas;
static GetCounter getCounter;
static IncrementCounter incrementCounter;
static SleepFn pauseThread;
static QueueFn enqueue;
static volatile U32 fieldVisits;
static ErrorGet errorGet;
static ErrorSet errorSet;
static U32 cryptoError,destroyError;
struct Encoder;
extern "C" __declspec(dllexport) __declspec(noinline) void fixture_destroy(void *);
struct Encoder {
 U32 value,mode;
 Encoder(U32 m):value(0),mode(m){}
 ~Encoder() noexcept(false) { fixture_destroy(this); }
};
extern "C" __declspec(dllexport) void fixture_configure(void *state,GetCounter get,IncrementCounter inc,SleepFn pause,QueueFn queue,ErrorGet getError,ErrorSet setError) {
 sas=state;getCounter=get;incrementCounter=inc;pauseThread=pause;enqueue=queue;errorGet=getError;errorSet=setError;
}
extern "C" __declspec(dllexport) __declspec(noinline) unsigned char fixture_encrypt(void *opaque,void *) {
 Encoder *ctx=(Encoder *)opaque;
 if(ctx->mode==6)cryptoError=errorGet();
 if(ctx->mode==1)return 0;
 if(ctx->mode==2)throw 2;
 if(ctx->mode==5){Encoder inner(0);if(fixture_encrypt(&inner,0))enqueue(inner.value);}
 U32 value=getCounter(sas);pauseThread(1);incrementCounter(sas);ctx->value=value;
 if(ctx->mode==3)throw 3;
 if(ctx->mode==6)errorSet(888);
 return 1;
}
extern "C" __declspec(dllexport) __declspec(noinline) void fixture_destroy(void *opaque) {
 Encoder *ctx=(Encoder *)opaque;
 if(ctx->mode==6){destroyError=errorGet();errorSet(999);}
 if(ctx->mode==4)throw 4;
 ctx->value=0;
}
extern "C" __declspec(dllexport) __declspec(noinline) int fixture_sender(void *,void *mode) {
 try {
  Encoder ctx((U32)(unsigned long long)mode);
  if(!fixture_encrypt(&ctx,0))return -1;
  enqueue(ctx.value);return 1;
 }catch(int value){return 100+value;}
}
extern "C" __declspec(dllexport) __declspec(noinline) void fixture_field(void *,void *) {pauseThread(0);fieldVisits++;}
extern "C" __declspec(dllexport) void fixture_unmatched_destroy() {Encoder ctx(0);}
extern "C" __declspec(dllexport) int fixture_error_probe() {
 errorSet(777);{Encoder ctx(6);fixture_encrypt(&ctx,0);}
 return cryptoError==777&&destroyError==888&&errorGet()==999;
}
