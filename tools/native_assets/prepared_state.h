#pragma once
#include "prepare.h"

// FindFirstFileEx supplies timestamps and sizes in the directory enumeration.
// Opening each of the tens of thousands of loose files here defeats the cache.
inline void scan_asset_metadata(const fs::path &directory, std::string prefix,
                                std::vector<std::string> &rows, Job &job) {
  job.check();
  WIN32_FIND_DATAW entry{};
  const auto handle = FindFirstFileExW((directory / L"*").c_str(),
      FindExInfoBasic, &entry, FindExSearchNameMatch, nullptr, FIND_FIRST_EX_LARGE_FETCH);
  if (handle == INVALID_HANDLE_VALUE) {
    require(GetLastError() == ERROR_FILE_NOT_FOUND, "Cannot enumerate asset metadata");
    return;
  }
  struct Search {
    HANDLE handle;
    ~Search() { FindClose(handle); }
  } search{handle};
  do {
    const std::wstring_view name(entry.cFileName);
    if (name == L"." || name == L".." || (prefix == "_runtime/" && name == L"prepared-state.json"))
      continue;
    require(!(entry.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT),
            "Linked paths are unsupported in loose assets");
    const auto relative = prefix + utf8(fs::path(name));
    if (entry.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)
      scan_asset_metadata(directory / name, relative + "/", rows, job);
    else
      rows.push_back(relative + '\0' +
          std::to_string((uint64_t(entry.nFileSizeHigh) << 32) | entry.nFileSizeLow) + '\0' +
          std::to_string((uint64_t(entry.ftLastWriteTime.dwHighDateTime) << 32) |
                         entry.ftLastWriteTime.dwLowDateTime));
  } while (FindNextFileW(handle, &entry));
  require(GetLastError() == ERROR_NO_MORE_FILES, "Cannot finish enumerating asset metadata");
}

inline std::string asset_metadata_state(const fs::path &root, Job &job, bool outputs) {
  std::vector<std::string> rows;
  if (!outputs) {
    for (auto name : {L"assets", L"_archive"}) {
      const auto directory = root / name;
      const auto attr = GetFileAttributesW(directory.c_str());
      if (attr == INVALID_FILE_ATTRIBUTES && std::wstring_view(name) == L"_archive" &&
          GetLastError() == ERROR_FILE_NOT_FOUND)
        continue;
      require(attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY) &&
              !(attr & FILE_ATTRIBUTE_REPARSE_POINT), "Invalid loose asset directory");
      scan_asset_metadata(directory, utf8(fs::path(name)) + "/", rows, job);
    }
  } else {
    const auto directory = root / L"_runtime";
    const auto attr = GetFileAttributesW(directory.c_str());
    require(attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY) &&
            !(attr & FILE_ATTRIBUTE_REPARSE_POINT), "Invalid runtime asset directory");
    scan_asset_metadata(directory, "_runtime/", rows, job);
  }
  const auto files = outputs ?
      std::vector{L"assets.map", L"native_dds.index", L"native_audio.index"} :
      std::vector{L"assets.json", L"scene_textures.json", L"asset_edits.json"};
  for (const auto file : files) {
    const auto full = root / file;
    if (!outputs && !fs::exists(full))
      continue;
    rows.push_back(utf8(fs::path(file)) + '\0' + file_sha(contained(root, utf8(fs::path(file)))));
  }
  std::sort(rows.begin(), rows.end());
  std::string state;
  for (const auto &row : rows) {
    state += row;
    state += '\n';
  }
  return sha({reinterpret_cast<const uint8_t *>(state.data()), state.size()});
}

inline J prepare_current(const fs::path &source, Job &job, bool reuse,
                         bool private_install = false) {
  auto root = longpath(fs::canonical(longpath(source)));
  const auto receipt = root / L"_runtime" / L"prepared-state.json";
  const auto before = private_install ? std::string() :
                                       asset_metadata_state(root, job, false);
  if (reuse && fs::is_regular_file(receipt)) {
    try {
      auto state = json(receipt);
      if (state.at("version") == 1 && state.at("inputs").get<std::string>() == before &&
          state.at("outputs").get<std::string>() == asset_metadata_state(root, job, true))
        return J{{"ready", true}, {"reused", true}};
    } catch (const std::exception &) {
      // Treat an interrupted or outdated publication as a cache miss.
    }
  }
  fs::remove(receipt);
  auto result = prepare(root, job);
  const auto after = asset_metadata_state(root, job, false);
  if (private_install || after == before)
    jsonwrite(receipt, J{{"version", 1}, {"inputs", after},
                         {"outputs", asset_metadata_state(root, job, true)}});
  result["reused"] = false;
  return result;
}

inline J initialize_sparse_overlay(const fs::path &base, const fs::path &stage,
                                   const J &folders, Job &job) {
  const auto root = longpath(fs::canonical(longpath(base)));
  const auto receipt = root / L"_runtime" / L"prepared-state.json";
  if (!fs::is_regular_file(receipt) ||
      fs::exists(root / L"asset_edits.json") ||
      !fs::is_regular_file(root / L"scene_textures.json"))
    return {{"eligible", false}};
  for (auto name : {L"native_dds.index", L"native_audio.index"}) {
    std::ifstream index(root / name);
    std::string line;
    if (!std::getline(index, line))
      return {{"eligible", false}};
    while (std::getline(index, line))
      if (!line.empty())
        return {{"eligible", false}};
  }
  auto stamp = json(receipt);
  if (stamp.at("version") != 1 ||
      stamp.at("inputs") != asset_metadata_state(root, job, false) ||
      stamp.at("outputs") != asset_metadata_state(root, job, true))
    return {{"eligible", false}};
  auto manifest = json(root / L"assets.json");
  if (!manifest.contains("loader_metadata"))
    return {{"eligible", false}};
  auto catalog = json(root / L"scene_textures.json");
  std::map<uint32_t, std::string> selected;
  J entries = J::array(), scenes = J::array();
  for (const auto &entry : manifest.at("entries")) {
    const auto name = entry.at("folder").get<std::string>();
    if (std::find(folders.begin(), folders.end(), name) == folders.end())
      continue;
    auto layout = json(contained(root, name) / L"asset.json");
    if (layout.contains("paired_owner") || layout.contains("paired_resources"))
      return {{"eligible", false}};
    selected.emplace(uint32_t(num(entry.at("hash"))), name);
    entries.push_back(entry);
  }
  require(selected.size() == folders.size(), "Mod bank is missing from the stock catalog");
  for (const auto &scene : catalog.at("scenes")) {
    const auto found = selected.find(uint32_t(num(scene.at("bank"))));
    if (found == selected.end())
      continue;
    for (const auto &item : scene.at("textures"))
      if (!item.at("file").get<std::string>().starts_with(found->second + "/"))
        return {{"eligible", false}};
    scenes.push_back(scene);
  }
  manifest["entries"] = std::move(entries);
  catalog["scenes"] = std::move(scenes);
  catalog["unsupported"] = J::array();
  jsonwrite(stage / L"assets.json", manifest);
  jsonwrite(stage / L"scene_textures.json", catalog);
  return {{"eligible", true}};
}
