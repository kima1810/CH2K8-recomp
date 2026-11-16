#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <bcrypt.h>
#include <atomic>
#include <algorithm>
#include <cfenv>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <immintrin.h>
#include <sstream>
#include <vector>
#include <set>
#include <rex/ppc.h>
#include <rex/logging.h>
#include <rex/cvar.h>
#include "../third_party/nlohmann/json.hpp"
#include "mod_extension_abi.h"
#include "mod_framework.h"

namespace {
namespace fs=std::filesystem;
constexpr const char* Xex="71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36";
std::atomic<ChmodReadWeightFnV1> weight_read{nullptr};
std::atomic<bool> warned{false};
std::atomic<bool> dispatched{false};
std::vector<HMODULE> retained_modules; // OS releases only after runtime teardown/process exit.
std::string digest(const fs::path& p) {
  BCRYPT_ALG_HANDLE alg=nullptr; BCRYPT_HASH_HANDLE hash=nullptr;
  if(BCryptOpenAlgorithmProvider(&alg,BCRYPT_SHA256_ALGORITHM,nullptr,0)<0)throw std::runtime_error("SHA256 provider unavailable");
  struct Cleanup{BCRYPT_ALG_HANDLE& a;BCRYPT_HASH_HANDLE& h;~Cleanup(){if(h)BCryptDestroyHash(h);if(a)BCryptCloseAlgorithmProvider(a,0);}}cleanup{alg,hash};
  if(BCryptCreateHash(alg,&hash,nullptr,0,nullptr,0,0)<0)throw std::runtime_error("SHA256 allocation failed");
  std::ifstream in(p,std::ios::binary);if(!in)throw std::runtime_error("Cannot read mod integrity input");
  std::vector<uint8_t> bytes(1<<20);
  while(in){in.read(reinterpret_cast<char*>(bytes.data()),bytes.size());auto n=in.gcount();if(n && BCryptHashData(hash,bytes.data(),ULONG(n),0)<0)throw std::runtime_error("SHA256 update failed");}
  if(!in.eof())throw std::runtime_error("Mod integrity read failed");
  uint8_t result[32];if(BCryptFinishHash(hash,result,32,0)<0)throw std::runtime_error("SHA256 finish failed");
  std::ostringstream text;for(auto c:result)text<<std::hex<<std::setw(2)<<std::setfill('0')<<unsigned(c);return text.str();
}
fs::path checked_file(const fs::path& root,const std::string& relative) {
  auto supplied=fs::path(std::u8string(relative.begin(),relative.end()));
  if(supplied.is_absolute() || supplied.has_root_name())throw std::runtime_error("Absolute extension path rejected");
  auto requested=fs::absolute(root)/supplied;
  for(auto p=requested;!p.empty();p=p.parent_path()){
    auto attr=GetFileAttributesW(p.c_str());
    if(attr!=INVALID_FILE_ATTRIBUTES && (attr&FILE_ATTRIBUTE_REPARSE_POINT))throw std::runtime_error("Linked extension path rejected");
    if(p==p.parent_path())break;
  }
  auto base=fs::canonical(root), full=fs::canonical(requested), rel=full.lexically_relative(base);
  if(rel.empty() || *rel.begin()==".." || !fs::is_regular_file(full))throw std::runtime_error("Extension path escapes mod installation");
  return full;
}
void check_pe(const fs::path& file) {
  auto size=fs::file_size(file);if(size<256 || size>(64ull<<20))throw std::runtime_error("Extension PE size invalid");
  std::ifstream input(file,std::ios::binary);std::vector<uint8_t> b(size);input.read(reinterpret_cast<char*>(b.data()),b.size());
  auto u16=[&](size_t p){if(p>b.size() || b.size()-p<2)throw std::runtime_error("Truncated PE");return unsigned(b[p])|unsigned(b[p+1])<<8;};
  auto u32=[&](size_t p){return uint32_t(u16(p))|uint32_t(u16(p+2))<<16;};
  if(!input || u16(0)!=0x5a4d)throw std::runtime_error("Invalid extension PE header");
  auto pe=u32(60);if(u32(pe)!=0x4550 || u16(pe+4)!=0x8664 || !(u16(pe+22)&0x2000) || u16(pe+24)!=0x20b)throw std::runtime_error("Extension must be a Windows x64 DLL");
}
}


namespace {
using ch2k8::mods::Framework;
using ch2k8::mods::Dispatch;
struct LoadedV2 { const ChmodHostV2* host; const ChmodExtensionV2* descriptor; };
std::vector<LoadedV2> loaded_v2;
struct NativeFpScope {
 std::fenv_t environment{};bool valid=std::fegetenv(&environment)==0;unsigned mxcsr=_mm_getcsr();
 ~NativeFpScope(){if(valid)std::fesetenv(&environment);_mm_setcsr(mxcsr);}
};
void shutdown_v2(){
 for(auto it=loaded_v2.rbegin();it!=loaded_v2.rend();++it){
  Framework::instance().discard(it->host->session);
  if(it->descriptor->shutdown)Framework::instance().initialize(it->host,[&]{it->descriptor->shutdown();return CHMOD_OK;});
 }
 loaded_v2.clear();
}
}
void Ch2k8EnablePresentation();
void Ch2k8PublishPresentation();
void Ch2k8ShutdownModExtensions(){
 weight_read.store(nullptr,std::memory_order_release);
 Framework::instance().stop();shutdown_v2(); // Handles deliberately never FreeLibrary.
}
bool Ch2k8ConfigureModExtensions(const std::filesystem::path& config,
                               bool opted_in,const std::filesystem::path& game) {
 if(config.empty())return true;
 auto& framework=Framework::instance();
 NativeFpScope fp;
 if(!fp.valid){REXLOG_ERROR("CHMOD cannot preserve initialization FP environment");return false;}
 framework.logger([](uint32_t level,const std::string& message){if(level>=2)REXLOG_WARN("CHMOD {}",message);else REXLOG_INFO("CHMOD {}",message);});
 try {
  if(!opted_in)throw std::runtime_error("Native extensions require explicit unsandboxed-code opt-in");
  if(fs::file_size(config)>(1u<<20))throw std::runtime_error("Mod launch configuration exceeds limit");
  nlohmann::json plan;std::ifstream(config)>>plan;
  if(plan.at("schema_version")!=1 || (plan.at("mod_api")!="1.2.0" && plan.at("mod_api")!="1.3.0") || plan.at("xex_sha256")!=Xex || digest(game/L"default.xex")!=Xex)throw std::runtime_error("Native extension runtime/game revision differs");
  const auto& extensions=plan.at("extensions");
  if(!extensions.is_array() || extensions.empty() || extensions.size()>64)throw std::runtime_error("Expected 1..64 native modules");
  const auto root_text=plan.at("mod_root").get<std::string>();
  const auto root=fs::path(std::u8string(root_text.begin(),root_text.end()));
  std::vector<fs::path> files;bool legacy=false,modern_read=false;uint32_t presentation=0;std::set<std::string> replacements,ids,emitted;
  for(const auto& e:extensions)if(!ids.insert(e.at("id").get<std::string>()).second)throw std::runtime_error("Duplicate native module identity");
  const auto cap_list=Framework::capabilities();const std::set<std::string> supported(cap_list.begin(),cap_list.end());
  for(const auto& e:extensions){
   for(const auto& dependency:e.value("dependencies",nlohmann::json::array())){
    auto id=dependency.get<std::string>();if(ids.contains(id) && !emitted.contains(id))throw std::runtime_error("Native modules must be dependency ordered: "+id);
   }
   emitted.insert(e.at("id").get<std::string>());
   if(e.at("abi")==1){if(legacy || e.at("hook")!="player.weight.read")throw std::runtime_error("ABI 1 weight hook is exclusive");legacy=true;}
   else if(e.at("abi")==2){
    if(plan.at("mod_api")!="1.3.0" || !e.at("capabilities").is_array() || e.at("capabilities").empty())throw std::runtime_error("ABI 2 requires API 1.3 and declared capabilities");
    std::set<std::string> seen;
    for(const auto& c:e.at("capabilities")){auto cap=c.get<std::string>();if(!supported.contains(cap) || !seen.insert(cap).second)throw std::runtime_error("Unsupported/duplicate required capability: "+cap);if(cap=="hook.player.weight.read")modern_read=true;if(cap=="hook.presentation.button_style")++presentation;}
    if(!e.at("replacements").is_array())throw std::runtime_error("Missing replacement claims");
    for(const auto& r:e.at("replacements")){auto name=r.get<std::string>();if((!std::any_of(Framework::inventory().begin(),Framework::inventory().end(),[&](const auto& h){return name==h.name && (h.operations&CHMOD_OP_REPLACE);})) || !seen.contains("hook."+name) || !replacements.insert(name).second)throw std::runtime_error("Invalid/conflicting exclusive replacement: "+name);}
   }else throw std::runtime_error("Unsupported extension ABI");
   auto file=checked_file(root,e.at("file").get<std::string>());check_pe(file);
   if(digest(file)!=e.at("sha256").get<std::string>())throw std::runtime_error("Extension integrity differs: "+e.at("id").get<std::string>());
   files.push_back(file);
  }
  if(legacy && modern_read)throw std::runtime_error("Legacy ABI 1 weight mod conflicts with ABI 2 weight-read registrations; disable one");
  if(presentation>1)throw std::runtime_error("Only one Button Style provider may be enabled");
  if(presentation && (rex::cvar::Query<uint32_t>("ch2k8_presentation_dds_api")!=1 || rex::cvar::GetFlagByName("ch2k8_renderer")!="d3d12" || !rex::cvar::Query<bool>("ch2k8_native_dds") || !fs::is_regular_file(game/"native_dds_choices.index")))throw std::runtime_error("Button Style requires the matching updated D3D12 GPU plugin, native DDS, and its coherent conditional-asset cache");
  ChmodReadWeightFnV1 legacy_callback=nullptr;
  for(size_t i=0;i<extensions.size();++i){
   const auto& e=extensions[i];
   // Recheck immediately before load. Modules remain unsandboxed (including DllMain).
   if(digest(files[i])!=e.at("sha256").get<std::string>())throw std::runtime_error("Extension changed before load");
   auto module=LoadLibraryExW(files[i].c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
   if(!module)throw std::runtime_error("Native extension dependency/load failure: "+e.at("id").get<std::string>());
   retained_modules.push_back(module);
   if(e.at("abi")==1){
    auto query=reinterpret_cast<ChmodQueryFnV1>(GetProcAddress(module,"ChmodQueryExtension"));
    if(!query)throw std::runtime_error("ABI 1 extension lacks ChmodQueryExtension");
    auto d=query(1);
    if(!d || d->size!=sizeof(ChmodExtensionV1) || d->abi_version!=1 || d->reserved_zero || !d->player_weight_read)throw std::runtime_error("ABI 1 descriptor incompatible");
    legacy_callback=d->player_weight_read;
   }else{
    auto query=reinterpret_cast<ChmodQueryFnV2>(GetProcAddress(module,"ChmodQueryExtensionV2"));
    if(!query)throw std::runtime_error("ABI 2 extension lacks ChmodQueryExtensionV2");
    auto d=query(2);
    if(!d || d->size!=sizeof(ChmodExtensionV2) || d->abi_version!=2 || !d->initialize)throw std::runtime_error("ABI 2 descriptor incompatible");
    const auto* host=framework.create_module(e.at("id").get<std::string>(),e.at("capabilities").get<std::vector<std::string>>(),e.at("replacements").get<std::vector<std::string>>());
    if(!host)throw std::runtime_error("Native module capacity/lifecycle rejected");
    loaded_v2.push_back({host,d});
    if(framework.initialize(host,[&]{return d->initialize(host);})!=CHMOD_OK)throw std::runtime_error("Extension initialization/registration failed: "+e.at("id").get<std::string>());
   }
   REXLOG_WARN("CHMOD unsandboxed module initialized: {} ABI {}",e.at("id").get<std::string>(),e.at("abi").get<int>());
  }
  weight_read.store(legacy_callback,std::memory_order_release);
  if(presentation)Ch2k8EnablePresentation();
  framework.publish();if(presentation)Ch2k8PublishPresentation();return true;
 }catch(const std::exception& e){weight_read=nullptr;framework.stop();shutdown_v2();REXLOG_ERROR("CHMOD initialization rejected: {}. Use Launch without mods.",e.what());return false;}
 catch(...){weight_read=nullptr;framework.stop();shutdown_v2();REXLOG_ERROR("CHMOD initialization threw; use Launch without mods");return false;}
}

REX_EXTERN(__imp__sub_84752968);
REX_EXTERN(__imp__sub_848425D8);
// Strong symbols override generated weak aliases for BOTH direct calls and the
// guest function map. Original bodies remain __imp__ names after regeneration.
REX_HOOK_RAW(sub_84752968) {
 const auto player=ctx.r3.u32;
 auto& framework=Framework::instance();
 if(!framework.enabled()){__imp__sub_84752968(ctx,base);return;}
 ChmodWeightReadArgs args{framework.next_player()};ChmodWeightReadResult result{};
 uint32_t baseline=0;bool called=false;
 auto original=[&]{__imp__sub_84752968(ctx,base);baseline=result.pounds=ctx.r3.u32;called=true;
  if(auto callback=weight_read.load(std::memory_order_acquire)){
   const ChmodWeightReadV1 event{sizeof(ChmodWeightReadV1),1,player,baseline};
   std::fenv_t environment;const auto mxcsr=_mm_getcsr();
   if(std::fegetenv(&environment)==0){try{auto v=callback(&event);if(v>=100 && v<=400)result.pounds=v;}catch(...){REXLOG_WARN("CHMOD legacy callback threw; retaining original");}std::fesetenv(&environment);_mm_setcsr(mxcsr);}
  }
 };
 auto read=[&]{auto copy=ctx;copy.r3.u64=player;__imp__sub_84752968(copy,base);return copy.r3.u32;};
 const auto token=args.player;
 auto d=ch2k8::mods::typed_call(1,args,result,original,[&]{return args.player==token && ((called && result.pounds==baseline) || (result.pounds>=100 && result.pounds<=400) || (!called && result.pounds==0));},read,token);
 d.validate_result=[&]{return (called && result.pounds==baseline) || (result.pounds>=100 && result.pounds<=400);};
 framework.dispatch(d);ctx.r3.u64=result.pounds;
}
REX_HOOK_RAW(sub_848425D8) {
 auto& framework=Framework::instance();if(!framework.enabled()){__imp__sub_848425D8(ctx,base);return;}
 const auto player=ctx.r3.u32;const auto incoming=ctx.r4.u32;
 ChmodWeightWriteArgs args{framework.next_player(),incoming,0};const auto token=args.player;
 auto original=[&]{ctx.r4.u64=args.pounds;__imp__sub_848425D8(ctx,base);};
 auto read=[&]{auto copy=ctx;copy.r3.u64=player;__imp__sub_84752968(copy,base);return copy.r3.u32;};
 auto d=ch2k8::mods::typed_void_call(2,args,original,[&]{return args.player==token && args.reserved_zero==0 && (args.pounds==incoming || (args.pounds>=100 && args.pounds<=400));},read,token);
 framework.dispatch(d);
}
