/* Runtime input adaptation; native registrars/calculators own every object. */
typedef unsigned char u8;
typedef unsigned int u32;
typedef unsigned long long u64;
extern u8 game_handle[], dungeon_vtable[], engine_global[];
extern u8 aggregate_slot[], flat_slot[], update_slot[];
extern u8 cooldown_get_slot[], cooldown_set_slot[];
extern u8 effect_slot[];
extern u8 valid_game(void *handle);
extern void *resolve_game(void *handle);
extern void *actor_model(void *actor);
extern u32 model_title(void *model);
extern float awakening_remaining(void *actor);
extern void remove_buff(void *actor, u32 template_id);
extern void vector_assign(void *destination, const void *source);

static void *pointer(void *p, u32 offset) { return *(void **)((u8 *)p+offset); }
static u32 word(void *p, u32 offset) { return *(u32 *)((u8 *)p+offset); }
/* The late gameplay VM no longer exposes the socket registration member.
 * This temporary Lua C closure forwards its sole table argument to the same
 * original parser; Lua owns the call frame and the original parser owns data. */
extern u8 register_socket(void *manager);
int idol_register_socket(void *vm) {
  register_socket(pointer(pointer(engine_global,0),0x4c0));
  return 0;
}
static int title_index(u32 title) {
  if (title<38070 || title>38130 || (title-38070)%10) return -1;
  return (title-38070)/10;
}
static u32 visual_cooldown_key(u32 option) {
  if(option>=200410 && option<=200430) {
    u32 phase=(option-200410)%3;
    if(phase==1 || phase==2)return 200410+phase;
  }
  return option;
}
float idol_cooldown_get(void *actor,u32 option) {
  return ((float (*)(void *,u32))pointer(cooldown_get_slot,0))(actor,visual_cooldown_key(option));
}
void idol_cooldown_set(void *actor,u32 option,float seconds) {
  ((void (*)(void *,u32,float))pointer(cooldown_set_slot,0))(actor,visual_cooldown_key(option),seconds);
}
/* All arguments after the first four occupy eight-byte Windows x64 stack
 * slots. Preserve their bits, including float fields, and change only the
 * native lifetime float in slot eight for our 21 exact registered names. */
u64 idol_effect(u64 manager,u64 out,u64 name,u64 actor,u64 p5,u64 p6,u64 p7,u64 p8,
                 u64 p9,u64 p10,u64 p11,u64 p12,u64 p13,u64 p14,u64 p15) {
  const char *names[21]={__IDOL_EFFECT_NAMES__};
  const unsigned short *text;
  u64 length=*(u64 *)(name+0x10),capacity=*(u64 *)(name+0x18);
  int i,j;
  union {float f;u32 bits;} limit;
  text=capacity<8?(const unsigned short *)name:*(const unsigned short **)name;
  for(i=0;i<21;i++) {
    for(j=0;names[i][j] && (u64)j<length && text[j]==(unsigned char)names[i][j];j++);
    if((u64)j==length && names[i][j]==0) {
      limit.f=i%3==0?0.9f:(i%3==1?2.0f:0.6f);
      p8=(p8&0xffffffff00000000ULL)|limit.bits;
      break;
    }
  }
  return ((u64 (*)(u64,u64,u64,u64,u64,u64,u64,u64,u64,u64,u64,u64,u64,u64,u64))pointer(effect_slot,0))
      (manager,out,name,actor,p5,p6,p7,p8,p9,p10,p11,p12,p13,p14,p15);
}
static int dungeon(void) {
  void *game;
  if (!valid_game(game_handle)) return 0;
  game=resolve_game(game_handle);
  return game && pointer(game,0)==dungeon_vtable;
}
static int actor_title(void *actor) {
  void *model;
  if (!actor || word(actor,0x3c4)!=0) return -1;
  model=actor_model(actor);
  return model ? title_index(model_title(model)) : -1;
}
/* Only the selected title's owned vector is adapted. Other socket sources and
 * original shared Title records are never edited. The native copy at 182D210
 * refreshes this vector before every aggregation, including mode changes. */
void idol_aggregate(void *actor,void *out,void *ids,float scale,u32 mode,u32 kind,void *values) {
  int index;
  u32 selected[__IDOL_SOCKET_COUNT__];
  void *vector[3];
  if (ids==(u8 *)actor+0x1a8d0 && dungeon() && (index=actor_title(actor))>=0) {
    __IDOL_SOCKET_VALUES__
    vector[0]=selected;vector[1]=selected+__IDOL_SOCKET_COUNT__;vector[2]=vector[1];
    vector_assign(ids,vector);
  }
  ((void (*)(void *,void *,void *,float,u32,u32,void *))pointer(aggregate_slot,0))
      (actor,out,ids,scale,mode,kind,values);
}
void *idol_flat(void *manager,void *out) {
  void *result=((void *(*)(void *,void *))pointer(flat_slot,0))(manager,out);
  void *engine=pointer(engine_global,0),*user,*model;
  if (dungeon() && engine && (user=pointer(engine,0xc8)) &&
      (model=pointer(user,0xa0)) && title_index(model_title(model))>=0) {
    *(float *)((u8 *)out+0x18)=0.0f;
    *(float *)((u8 *)out+0x1c)=0.0f;
  }
  return result;
}
/* Run before the native Actor buff loop. Removing inside its iteration would
 * invalidate iterators. Native RemoveBuff restores modifiers and displayers. */
void idol_update(void *actor,float delta) {
  int index=actor_title(actor),active=dungeon(),i;
  void **p,**end;
  u32 remove=0,id;
  static const u32 high[5]={2000,1056,2170,2867,3446};
  if (actor && word(actor,0x3c4)==0) {
    p=(void **)pointer(actor,0x1858);end=(void **)pointer(actor,0x1860);
    for(;p!=end;p++) {
      if (!*p) continue;
      id=word(*p,0x50);
      if (id>=3457 && id<=3463) {
        if (!active || index<0 || id!=(u32)(3457+index) || !(awakening_remaining(actor)>0.0f))
          remove|=1U<<(id-3457);
      } else if (active && index>=0) {
        for(i=0;i<5;i++)if(id==high[i]) {remove|=1U<<(7+i);break;}
      }
    }
    for(i=0;i<12;i++)if(remove&(1U<<i))remove_buff(actor,i<7?(u32)(3457+i):high[i-7]);
  }
  ((void (*)(void *,float))pointer(update_slot,0))(actor,delta);
}
