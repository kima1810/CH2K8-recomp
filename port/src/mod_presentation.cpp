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
#include <string_view>
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
uint32_t score_cells=0;
std::atomic<uint32_t> network{0};
std::atomic<uint32_t> active_scorebug{2};
using ScorebugChoice = uint32_t(*)(uint32_t, uint32_t);
ScorebugChoice scorebug_choice=nullptr;
std::filesystem::path network_preference;
uint32_t cells=0; // Label and two native managed string cells, rooted until exit.
std::filesystem::path preference;
}
REX_EXTERN(__imp__sub_847DC530);
REX_EXTERN(__imp__sub_848635D8);
REX_EXTERN(__imp__sub_84863460);
REX_EXTERN(__imp__sub_84746438);
REX_EXTERN(__imp__sub_84D275A0);
REX_EXTERN(__imp__sub_84D27690);


void Ch2k8PreparePresentation(rex::Runtime& r){
 runtime=&r;
 wchar_t provider[32768]{};
 const auto size=GetEnvironmentVariableW(L"CH2K8_SCOREBUG_PROVIDER",provider,DWORD(std::size(provider)));
 if(!size || size>=std::size(provider))return;
 const auto directory=rex::to_path(rex::cvar::GetFlagByName("game_data_root"));
 if(!std::filesystem::is_regular_file(directory/"scorebug-probe.ready"))return;
 const std::filesystem::path path(provider);
 if(!path.is_absolute() || path.filename()!=L"scorebug-preview.dll")return;
 const auto module=LoadLibraryExW(path.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
 if(!module)return;
 scorebug_choice=reinterpret_cast<ScorebugChoice>(GetProcAddress(module,"Ch2k8ScorebugChoice"));
 if(!scorebug_choice){FreeLibrary(module);return;}
 network_preference=rex::to_path(rex::cvar::GetFlagByName("user_data_root"))/"chmod-scorebug-preview.json";
 try{
  if(std::filesystem::is_regular_file(network_preference) && std::filesystem::file_size(network_preference)<128){
   nlohmann::json saved;std::ifstream(network_preference)>>saved;
   const auto choice=saved.at("network").get<uint32_t>();
   if(saved.at("version")==1 && choice<=1)network=choice;
  }
 }catch(...){REXLOG_WARN("Scorebug preview preference unreadable; using ESPN");}
 REXLOG_INFO("Scorebug preview provider loaded; network {}",network.load());
}
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

void network_scalar(PPCContext& ctx,uint8_t*){ctx.r3.u64=network.load();}
void network_toggle(PPCContext& ctx,uint8_t*){
 std::lock_guard lock(menu_mutex);
 if(scorebug_choice){
  const auto choice=scorebug_choice(1,network.load());
  if(choice<=1){
   network=choice;
   try{
    auto temp=network_preference;temp+=".tmp";
    {std::ofstream out(temp,std::ios::binary|std::ios::trunc);out<<"{\"version\":1,\"network\":"<<choice<<"}\n";
     out.flush();if(!out)throw std::runtime_error("write failed");}
    if(!MoveFileExW(temp.c_str(),network_preference.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH))
     throw std::runtime_error("replace failed");
   }catch(...){REXLOG_WARN("Scorebug choice saved for this session only");}
  }
 }
 ctx.r3.u64=1;
}
void network_text(PPCContext& ctx,uint8_t* base){ctx.r4.u64=score_cells+4+4*network.load();ctx.r5.u64=0;__imp__sub_84863460(ctx,base);}
void network_width(PPCContext& ctx,uint8_t* base){ctx.r4.u64=0;ctx.r5.u64=1;ctx.r6.u64=score_cells+8;__imp__sub_84746438(ctx,base);}

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
 const auto row_count=Count+unsigned(enabled)+unsigned(scorebug_choice!=nullptr);
 const auto allocation=runtime->memory()->SystemHeapAlloc(row_count*item_size+512);
 if(!allocation)throw std::runtime_error("Presentation guest allocation failed");
 std::memset(base+allocation,0,row_count*item_size+512);
 std::memcpy(base+allocation,base+Rows,Count*item_size);
 auto next_row=allocation+Count*item_size;
 auto next_cells=allocation+row_count*item_size;
 auto cursor=next_cells+32;
 auto append=[&](uint32_t& out_cells,const char16_t* (&labels)[3],PPCFunc* get,PPCFunc* change,
                 PPCFunc* text_value,PPCFunc* measure){
  out_cells=next_cells;
  next_cells+=12;
  for(uint32_t i=0;i<3;++i){
   uint32_t j=0;
   for(;labels[i][j];++j){const auto v=std::byteswap(uint16_t(labels[i][j]));std::memcpy(base+cursor+j*2,&v,2);}
   auto ctx=source;ctx.r3.u64=out_cells+i*4;ctx.r4.u64=cursor;
   __imp__sub_848635D8(ctx,base);
   if(!read(out_cells+i*4))throw std::runtime_error("Presentation native string allocation failed");
   cursor+=(j+1)*2;
  }
  const auto row=next_row;
  next_row+=item_size;
  clone_item(base,row,choice_row);
  write_word(base,row+item_label,out_cells);
  const auto increment=allocate_callback(*dispatcher,base,change);
  set_callback(base,row,Callback::minimum,allocate_callback(*dispatcher,base,minimum));
  set_callback(base,row,Callback::maximum,allocate_callback(*dispatcher,base,maximum));
  set_callback(base,row,Callback::get,allocate_callback(*dispatcher,base,get));
  set_callback(base,row,Callback::decrement,increment);
  set_callback(base,row,Callback::increment,increment);
  set_callback(base,row,Callback::text,allocate_callback(*dispatcher,base,text_value));
  set_callback(base,row,Callback::width,allocate_callback(*dispatcher,base,measure));
 };
 if(enabled){
  const char16_t* labels[]={u"Button Style",u"Xbox",u"PlayStation"};
  append(cells,labels,scalar,toggle,text,width);
 }
 if(scorebug_choice){
  const char16_t* labels[]={u"Scorebug",u"ESPN",u"USA Sports"};
  append(score_cells,labels,network_scalar,network_toggle,network_text,network_width);
 }
 auto* heap=runtime->memory()->LookupHeap(Definition);uint32_t previous=0;
 if(!heap || !heap->Protect(Definition,80,rex::memory::kMemoryProtectRead|rex::memory::kMemoryProtectWrite,&previous))throw std::runtime_error("Presentation definition protection failed");
 write_word(base,Definition+item_array,allocation);
 write_word(base,Definition+item_count,row_count);
 if(!heap->Protect(Definition,80,previous,nullptr))REXLOG_WARN("CHMOD Presentation definition protection restore failed");
 installed=true;
 if(enabled)select(CHMOD_BUTTON_STYLE_QUERY);
 if(scorebug_choice)REXLOG_INFO("Scorebug preview Presentation row installed");
 REXLOG_INFO("CHMOD native Options/Presentation Button Style row installed (SDK hook 5)");
}
}
// Strong wrapper intercepts generated direct calls AND the guest dispatch map.
// __imp__ remains the generated original across code regeneration.
REX_HOOK_RAW(sub_847DC530){
 if(runtime && !rejected && (scorebug_choice || (enabled && ch2k8::mods::Framework::instance().enabled())) && (ctx.r4.u32==1 || ctx.r4.u32==3)){
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
rex::Runtime* Ch2k8ScorebugRuntime(){return scorebug_choice && active_scorebug.load()<2 ? runtime : nullptr;}
uint32_t Ch2k8ScorebugStyle(){return active_scorebug.load();}

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

// Opt-in trial for the regular Xbox bottom-bar scene. The alternate IDs
// are supplied only by the separately generated research bank.
REX_HOOK_RAW(sub_84D27690) {
 constexpr uint32_t GameData = 0x3df16510;
 constexpr uint32_t BottomBar = 0x3e691786;
 constexpr uint32_t Scene = 0xe26c9b5d;
 static const bool tracing = GetEnvironmentVariableW(L"CH2K8_TRACE_SCOREBUG", nullptr, 0) > 0;
 static const uint32_t probe_alias = [] {
  wchar_t value[8]{};
  const auto length = GetEnvironmentVariableW(L"CH2K8_SCOREBUG_PROBE", value, 8);
  if (length != 3 && length != 4) return uint32_t(0);
  if (std::wstring_view(value) == L"ESPN") return uint32_t(0x3ab5ef46);
  if (std::wstring_view(value) == L"USA") return uint32_t(0x79427bab);
  return uint32_t(0);
 }();
 const auto alias=scorebug_choice ? (network.load()?0x79427babu:0x3ab5ef46u) : probe_alias;
 static std::atomic<unsigned> hits{0};
 const bool scorebug = ctx.r5.u32 == GameData && ctx.r6.u32 == BottomBar && ctx.r7.u32 == Scene;
 if (!scorebug || (!tracing && !alias)) {
  __imp__sub_84D27690(ctx, base);
  return;
 }
 const auto caller = ctx.lr;
 const auto options = ctx.r4.u32;
 bool used_alias = false;
 if (alias) {
  const auto original = ctx;
  ctx.r6.u64 = alias;
  __imp__sub_84D27690(ctx, base);
  used_alias = ctx.r3.u32 != 0;
  if (!used_alias) ctx = original;
 }
 if (!used_alias) __imp__sub_84D27690(ctx, base);
 if(static_cast<uint32_t>(caller)==0x84aee40c)
  active_scorebug=used_alias?(alias==0x79427babu?1u:0u):2u;
 const auto sequence = hits.fetch_add(1, std::memory_order_relaxed);
 if (sequence < 32) {
  REXLOG_INFO("Scorebug lookup #{}: record={:08x}, return={:08x}, caller={:08x}, options={:08x}",
              sequence+1, used_alias ? alias : BottomBar, ctx.r3.u32,
              static_cast<uint32_t>(caller), options);
 }
}
