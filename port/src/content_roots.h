#pragma once
#include <cstdint>
#include <set>
#include <utility>

namespace ch2k8 {
// De-duplicate physical enumeration roots, never saves by display name.
// The current-title sentinel and the concrete title identify the same root.
class ContentRoots {
 public:
  bool First(uint64_t xuid, uint32_t title, uint32_t current_title) {
    if (title == UINT32_MAX) title = current_title;
    return roots_.emplace(xuid, title).second;
  }
 private:
  std::set<std::pair<uint64_t, uint32_t>> roots_;
};
}
