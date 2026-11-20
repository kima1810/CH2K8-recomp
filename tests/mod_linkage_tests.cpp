#include <stdexcept>
extern "C" int __imp__fixture(int);
extern "C" int fixture(int value){return __imp__fixture(value)+1;}
int main(){int (*map)(int)=fixture;if(fixture(4)!=5 || map(4)!=5 || __imp__fixture(4)!=4)throw std::runtime_error("direct/map override failed");}
