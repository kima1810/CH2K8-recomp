#pragma once
#include "../../sdk/include/chmod/abi.h"
#include <functional>
#include <memory>
#include <span>
#include <string>
#include <vector>
#include <type_traits>
namespace ch2k8::mods {
struct Dispatch {
 uint32_t hook;
 std::span<std::byte> arguments, result;
 std::function<void()> original;
 std::function<bool()> validate;
 std::function<uint32_t()> read_weight;
 ChmodPlayer player=0;
 std::function<bool()> validate_result;
};
class Framework {
public:
 struct Module;
 using Logger=std::function<void(uint32_t,const std::string&)>;
 static Framework& instance();
 void logger(Logger);
 const ChmodHostV2* create_module(std::string id,std::vector<std::string> capabilities,std::vector<std::string> replacements={});
 ChmodStatus initialize(const ChmodHostV2*,const std::function<ChmodStatus()>&);
 void discard(uint64_t session);
 void publish();
 void stop(); // suppress new dispatch, drain, then stopping notification; no unload
 void dispatch(Dispatch&);
 ChmodPlayer next_player();
 bool enabled()const;
 static const std::vector<ChmodHookInfo>& inventory();
 static std::vector<std::string> capabilities();
private:
 Framework();
 struct State; std::unique_ptr<State> state_;
 static ChmodStatus CHMOD_CALL discover(uint64_t,uint32_t,ChmodHookInfo*);
 static ChmodStatus CHMOD_CALL capability(uint64_t,const char*);
 static ChmodStatus CHMOD_CALL add(uint64_t,const ChmodRegistrationSpec*,ChmodRegistration*);
 static ChmodStatus CHMOD_CALL remove(uint64_t,ChmodRegistration);
 static ChmodStatus CHMOD_CALL original(uint64_t,uint64_t);
 static ChmodStatus CHMOD_CALL read_weight(uint64_t,ChmodPlayer,uint32_t*);
 static ChmodStatus CHMOD_CALL set_weight(uint64_t,ChmodPlayer,uint32_t);
 static ChmodStatus CHMOD_CALL log(uint64_t,uint32_t,const char*,uint32_t);
};
template<class T> std::span<std::byte> bytes(T& value){return std::as_writable_bytes(std::span(&value,1));}
template<class Args,class Result>
Dispatch typed_call(uint32_t hook,Args& args,Result& result,std::function<void()> original,
                    std::function<bool()> validate,std::function<uint32_t()> read={},ChmodPlayer player=0){
 static_assert(std::is_trivially_copyable_v<Args> && std::is_trivially_copyable_v<Result>);
 return {hook,bytes(args),bytes(result),std::move(original),std::move(validate),std::move(read),player};
}
template<class Args>
Dispatch typed_void_call(uint32_t hook,Args& args,std::function<void()> original,
                         std::function<bool()> validate,std::function<uint32_t()> read={},ChmodPlayer player=0){
 static_assert(std::is_trivially_copyable_v<Args>);
 return {hook,bytes(args),{},std::move(original),std::move(validate),std::move(read),player};
}
}
