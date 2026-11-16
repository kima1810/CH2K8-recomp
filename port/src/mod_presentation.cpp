#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <bit>
#include <rex/runtime.h>
#include <rex/ppc.h>
#include <rex/logging.h>
#include <rex/system/function_dispatcher.h>
#include <atomic>
#include <cstring>
#include <fstream>
#include <mutex>
#include "mod_framework.h"
#include "mod_option_menu.h"
#include "../third_party/nlohmann/json.hpp"

REXCVAR_DEFINE_BOOL(ch2k8_button_style,false,"CH2K8/Mods","Internal SDK Presentation texture selection");
namespace {
constexpr uint32_t Definition=0x8214c288, Rows=0x85548a28, Count=24;
rex::Runtime* runtime=nullptr;
bool enabled=false, installed=false, rejected=false;
std::recursive_mutex menu_mutex;
std::atomic<uint32_t> style{0};
uint32_t cells=0; // Label and two native managed string cells, rooted until exit.
std::filesystem::path preference;
}
REX_EXTERN(__imp__sub_847DC530);
REX_EXTERN(__imp__sub_848635D8);
REX_EXTERN(__imp__sub_84863460);
REX_EXTERN(__imp__sub_84746438);
REX_EXTERN(__imp__sub_84D275A0);

void Ch2k8PreparePresentation(rex::Runtime& r){runtime=&r;}
void Ch2k8EnablePresentation(){
 enabled=true;
 preference=rex::to_path(rex::cvar::GetFlagByName("user_data_root"))/"chmod-button-style.json";
 try {
  if(std::filesystem::is_regular_file(preference) && std::filesystem::file_size(preference)<128){
   nlohmann::json p;std::ifstream(preference)>>p;
   if(p.at("version")==1 && p.at("style").is_number_unsigned() && p.at("style").get<uint32_t>()<=1)style=p.at("style").get<uint32_t>();
  }
 }catch(...){REXLOG_WARN("CHMOD Button Style preference unreadable; using Xbox");}
}
namespace {
void select(uint32_t action){
 using namespace ch2k8::mods;
 const auto old=style.load();
 ChmodButtonStyleArgs args{action,old};ChmodButtonStyleResult result{};
 auto d=typed_call(CHMOD_HOOK_BUTTON_STYLE,args,result,[&]{result.style=0;},
  [&]{return args.action==action && args.current_style==old && result.style<=1;});
 Framework::instance().dispatch(d);
 style=result.style;
 rex::cvar::SetFlagByName("ch2k8_button_style",result.style?"true":"false");
 if(action==CHMOD_BUTTON_STYLE_TOGGLE){
  try {
   std::filesystem::create_directories(preference.parent_path());
   auto temp=preference;temp+=".tmp";
   {std::ofstream out(temp,std::ios::binary|std::ios::trunc);out<<"{\"version\":1,\"style\":"<<result.style<<"}\n";out.flush();if(!out)throw std::runtime_error("write failed");}
   // Atomic preference replacement, kept outside native game saves.
   if(!MoveFileExW(temp.c_str(),preference.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))throw std::runtime_error("replace failed");
  }catch(...){REXLOG_WARN("CHMOD Button Style selected for this session; preference could not be saved");}
 }
}
void scalar(PPCContext& ctx,uint8_t*){ctx.r3.u64=style.load();}
void minimum(PPCContext& ctx,uint8_t*){ctx.r3.u64=0;}
void maximum(PPCContext& ctx,uint8_t*){ctx.r3.u64=1;}
void toggle(PPCContext& ctx,uint8_t*){std::lock_guard lock(menu_mutex);select(CHMOD_BUTTON_STYLE_TOGGLE);ctx.r3.u64=1;}
void text(PPCContext& ctx,uint8_t* base){ctx.r4.u64=cells+4+4*style.load();ctx.r5.u64=0;__imp__sub_84863460(ctx,base);}
void width(PPCContext& ctx,uint8_t* base){ctx.r4.u64=0;ctx.r5.u64=1;ctx.r6.u64=cells+8;__imp__sub_84746438(ctx,base);}

void install(PPCContext& source,uint8_t* base){
 using namespace ch2k8::mods::option_menu;
 auto read=[&](uint32_t a){return read_word(base,a);};
 if(read(Definition+4)!=0x846d9158 || read(Definition+12)!=0x847dc530 ||
    read(Definition+item_array)!=Rows || read(Definition+item_count)!=Count || read(Rows)!=5 ||
    read(Rows+item_visibility)!=0 || read(Rows+20)!=0x847f49c8 || read(Rows+32)!=0x84c73cc0)
  throw std::runtime_error("Presentation row table differs from researched XEX");
 auto* dispatcher=runtime->function_dispatcher();
 uint32_t choice_row=0;
 for(uint32_t i=0;i<Count;++i){
  const auto candidate=Rows+i*item_size;
  if(read(candidate)==7 && !read(candidate+item_visibility)){choice_row=candidate;break;}
 }
 if(!choice_row)throw std::runtime_error("Presentation enum row is missing");
 const auto get=allocate_callback(*dispatcher,base,scalar);
 const auto min=allocate_callback(*dispatcher,base,minimum);
 const auto max=allocate_callback(*dispatcher,base,maximum);
 const auto change=allocate_callback(*dispatcher,base,toggle);
 const auto label=allocate_callback(*dispatcher,base,text);
 const auto measure=allocate_callback(*dispatcher,base,width);
 // Allocate before publishing anything. Failed preparation leaves stock menu intact.
 const auto allocation=runtime->memory()->SystemHeapAlloc((Count+1)*item_size+256);
 if(!allocation)throw std::runtime_error("Presentation guest allocation failed");
 cells=allocation+(Count+1)*item_size;
 std::memset(base+allocation,0,(Count+1)*item_size+256);
 std::memcpy(base+allocation,base+Rows,Count*item_size);
 const char16_t* labels[]={u"Button Style",u"Xbox",u"PlayStation"};
 auto cursor=cells+16;
 for(uint32_t i=0;i<3;++i){
  uint32_t j=0;for(;labels[i][j];++j){const auto v=std::byteswap(uint16_t(labels[i][j]));std::memcpy(base+cursor+j*2,&v,2);}
  auto ctx=source;ctx.r3.u64=cells+i*4;ctx.r4.u64=cursor;
  // 848635D8 -> 84864758 -> 84D5A028: literal UTF-16 expression,
  // retaining its source pointer; both source and root survive until process exit.
  __imp__sub_848635D8(ctx,base);
  if(!read(cells+i*4))throw std::runtime_error("Presentation native string allocation failed");
  cursor+=(j+1)*2;
 }
 const auto row=allocation+Count*item_size;
 clone_item(base,row,choice_row);
 write_word(base,row+item_label,cells);
 set_callback(base,row,Callback::minimum,min);
 set_callback(base,row,Callback::maximum,max);
 set_callback(base,row,Callback::get,get);
 set_callback(base,row,Callback::decrement,change);
 set_callback(base,row,Callback::increment,change);
 set_callback(base,row,Callback::text,label);
 set_callback(base,row,Callback::width,measure);
 auto* heap=runtime->memory()->LookupHeap(Definition);uint32_t previous=0;
 if(!heap || !heap->Protect(Definition,80,rex::memory::kMemoryProtectRead|rex::memory::kMemoryProtectWrite,&previous))throw std::runtime_error("Presentation definition protection failed");
 write_word(base,Definition+item_array,allocation);
 write_word(base,Definition+item_count,Count+1);
 if(!heap->Protect(Definition,80,previous,nullptr))REXLOG_WARN("CHMOD Presentation definition protection restore failed");
 installed=true;
 select(CHMOD_BUTTON_STYLE_QUERY);
 REXLOG_INFO("CHMOD native Options/Presentation Button Style row installed (SDK hook 5)");
}
}
// Strong wrapper intercepts generated direct calls AND the guest dispatch map.
// __imp__ remains the generated original across code regeneration.
REX_HOOK_RAW(sub_847DC530){
 if(enabled && runtime && !rejected && ch2k8::mods::Framework::instance().enabled() && (ctx.r4.u32==1 || ctx.r4.u32==3)){
  std::lock_guard lock(menu_mutex);
  const auto controller=ctx.r3.u32;
  const auto depth=std::byteswap(*reinterpret_cast<uint32_t*>(base+controller+228));
  if(depth<16 && std::byteswap(*reinterpret_cast<uint32_t*>(base+controller+4*(depth+2)))==Definition && !installed){
   try{install(ctx,base);}catch(const std::exception& e){rejected=true;rex::cvar::SetFlagByName("ch2k8_button_style","false");REXLOG_ERROR("CHMOD Button Style adapter rejected: {}",e.what());}
  }
 }
 __imp__sub_847DC530(ctx,base);
}
void Ch2k8PublishPresentation(){std::lock_guard lock(menu_mutex);select(CHMOD_BUTTON_STYLE_QUERY);}

REX_HOOK_RAW(sub_84D275A0) {
 constexpr uint32_t XboxControllerScene = 0x525ca356;
 constexpr uint32_t PlayStationControllerScene = 0x4d0b8a4f;
 constexpr uint32_t SceneType = 0xe26c9b5d;
 // Controller Setup's LAYT requests the Xbox SCNE by name each time it
 // instantiates the menu. Use the complete PS3 scene so its callout
 // geometry, labels and controller illustration agree.
 if (ctx.r5.u32 == XboxControllerScene && ctx.r6.u32 == SceneType &&
     style.load(std::memory_order_relaxed) == 1) {
  const auto original = ctx;
  ctx.r5.u64 = PlayStationControllerScene;
  __imp__sub_84D275A0(ctx, base);
  if (ctx.r3.u32) {
   REXLOG_INFO("CHMOD Controller Setup selected PlayStation scene");
   return;
  }
  ctx = original;
 }
 __imp__sub_84D275A0(ctx, base);
}
