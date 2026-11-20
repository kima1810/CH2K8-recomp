#include <cstdint>

extern "C" __declspec(dllexport) uint32_t Ch2k8ScorebugChoice(uint32_t action, uint32_t choice) {
    if (choice > 1) choice = 0;
    return action == 1 ? choice ^ 1u : choice;
}
