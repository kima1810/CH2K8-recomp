#pragma once
#include <algorithm>
#include <filesystem>
namespace ch2k8 {
// Keep long Win32 paths usable without changing machine-wide registry settings.
inline std::filesystem::path NativePath(const std::filesystem::path &path) {
#ifdef _WIN32
  auto value = std::filesystem::absolute(path).lexically_normal().native();
  std::replace(value.begin(), value.end(), L'/', L'\\');
  if (value.starts_with(L"\\\\?\\"))
    return std::filesystem::path(value);
  if (value.starts_with(L"\\\\"))
    return std::filesystem::path(L"\\\\?\\UNC\\" + value.substr(2));
  return std::filesystem::path(L"\\\\?\\" + value);
#else
  return path;
#endif
}
} // namespace ch2k8
