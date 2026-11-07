#include "../port/src/loose_archive.h"
#include "native_assets/disc.h"
#include "native_assets/prepare.h"
constexpr const char *SupportedXex =
    "71e8983d1cc009e485696aad19b5fa4b4661761870e2c8972717b932c1e4be36";
J inspect(Disc &disc, Archive &archive, const std::string &expected, Job &job) {
  job.check();
  auto xex = disc.member("default.xex", 0, disc.size("default.xex"));
  auto hash = sha(xex);
  require(hash == expected,
          "Unsupported default.xex revision. Observed SHA256: " + hash +
              "; compiled revision: " + expected +
              ". Legitimacy is not determined by this hash. A different "
              "revision needs compatible generated code; include this hash in "
              "a compatibility report. Input was left unchanged.");
  return J{{"image_bytes", disc.iso ? fs::file_size(disc.source) : 0},
           {"xex_sha256", hash},
           {"archive_parts", archive.parts.size()},
           {"archive_entries", archive.entries.size()},
           {"archive_bytes", archive.total},
           {"partition_base", disc.base},
           {"supported", true}};
}
J import_game(const fs::path &image, const fs::path &destination, Job &job,
              const std::string &expected) {
  auto output = longpath(destination);
  require(!fs::exists(output), "Installation folder already exists; existing "
                               "folders are never overwritten");
  require(fs::is_directory(output.parent_path()),
          "Choose an existing parent folder");
  job.update(0, 0, "Checking Xbox image identity and archive extents...");
  Disc disc(image);
  Archive archive(disc);
  auto validation = inspect(disc, archive, expected, job);
  auto space = fs::space(output.parent_path());
  require(space.available >= archive.total + (1ull << 30),
          "Not enough disk space for ISO import (decoded assets may require "
          "more than the archive size)");
  fs::path staging;
  std::random_device random;
  bool created = false;
  for (unsigned i = 0; i < 16 && !created; ++i) {
    staging = output.parent_path() /
              path(".ch2k8-import-" + hex(GetCurrentProcessId()) + "-" +
                   hex(random()));
    created = fs::create_directory(staging);
  }
  require(created, "Cannot create a private ISO staging folder");
  auto cleanup = [&]() {
    auto owned = longpath(fs::weakly_canonical(longpath(staging)));
    require(owned.parent_path() ==
                    longpath(fs::canonical(longpath(output.parent_path()))) &&
                utf8(owned.filename()).starts_with(".ch2k8-import-") &&
                !(GetFileAttributesW(staging.c_str()) &
                  FILE_ATTRIBUTE_REPARSE_POINT),
            "Unsafe import staging location; cleanup refused");
    fs::remove_all(longpath(owned));
  };
  try {
    auto game = longpath(staging / L"game");
    fs::create_directories(game / L"assets");
    write(game / L"default.xex",
          disc.member("default.xex", 0, disc.size("default.xex")));
    J manifest{{"version", 1},
               {"platform", "xbox360"},
               {"storage", "loose-resources"},
               {"total", archive.total},
               {"entries", J::array()},
               {"loader_metadata", archive.compatibility()}};
    auto entries = archive.entries;
    std::sort(entries.begin(), entries.end(),
              [](auto &a, auto &b) { return a.offset < b.offset; });
    auto names = candidate_names();
    uint64_t done = 0;
    for (auto &e : entries) {
      job.update(done, entries.size(),
                 "Extracting editable Xbox assets: " + std::to_string(done) +
                     "/" + std::to_string(entries.size()));
      auto data = archive.read(e.offset, e.size);
      auto it = names.find(e.hash);
      auto name =
          it == names.end() ? "hash_" + hex(e.hash) + ".iff" : it->second;
      auto folder = game / L"assets" / path(name);
      require(fs::create_directory(folder), "Duplicate imported asset folder");
      jsonwrite(folder / L"asset.json", explode(data, folder));
      manifest["entries"].push_back(J{{"index", e.index},
                                      {"hash", e.hash},
                                      {"offset", e.offset},
                                      {"size", e.size},
                                      {"folder", "assets/" + name},
                                      {"sha256", sha(data)}});
      ++done;
    }
    jsonwrite(game / L"assets.json", manifest);
    job.update(done, done, "Splitting paired Xbox resources...");
    materialize(game, manifest, job, false);
    job.update(done, done, "Validating native loose resource maps...");
    prepare(game, job);
    jsonwrite(game / L"iso-validation.json", validation);
    job.update(done, done, "Finalizing loose asset installation...");
    require(!fs::exists(output),
            "Destination appeared during import; it was left untouched");
    fs::rename(game, longpath(output));
    cleanup();
    return J{{"game_data", utf8(fs::canonical(output))},
             {"storage", "loose-resources"}};
  } catch (...) {
    auto error = std::current_exception();
    cleanup();
    std::rethrow_exception(error);
  }
}
int wmain(int argc, wchar_t **argv) {
  try {
    SetConsoleOutputCP(CP_UTF8);
    std::vector<std::string> a;
    for (int i = 1; i < argc; ++i)
      a.push_back(utf8(fs::path(argv[i])));
    require(!a.empty(), "Usage: ch2k8_tools inspect ISO | import ISO "
                        "NEW_FOLDER | prepare GAME_FOLDER");
    Job job;
    std::string expected = SupportedXex;
    std::vector<std::string> pos;
    for (size_t i = 0; i < a.size(); ++i) {
      if (a[i] == "--progress-file" || a[i] == "--cancel-file" ||
          a[i] == "--expected-xex-sha256") {
        auto option = a[i];
        require(++i < a.size(), "Missing option value");
        if (option == "--progress-file")
          job.progress = path(a[i]);
        else if (option == "--cancel-file")
          job.cancel = path(a[i]);
        else {
          expected = lower(a[i]);
          require(std::regex_match(expected, std::regex("[0-9a-f]{64}")),
                  "Invalid expected XEX SHA256");
        }
      } else
        pos.push_back(a[i]);
    }
    require(!pos.empty(), "Missing native tool command");
    J result;
    if (pos[0] == "version" || pos[0] == "--version")
      result = {
          {"tool", "ch2k8_tools"},
          {"version", 1},
          {"python_required", false},
          {"features", J::array({"iso", "xex-extraction", "direct-resources",
                                 "native-dds", "native-pcm"})}};
    else if (pos[0] == "validate-runtime") {
      require(pos.size() == 2, "Usage: validate-runtime GAME_FOLDER");
      ch2k8::LooseArchive archive(path(pos[1]));
      std::array<uint8_t, 16> bytes{};
      for (const auto &part : archive.parts()) {
        require(archive.Read(part.offset, bytes) == bytes.size(),
                "Runtime map read failed");
      }
      result = {{"ready", true}, {"parts", archive.parts().size()}};
    } else if (pos[0] == "inspect") {
      require(pos.size() == 2, "Usage: inspect ISO");
      Disc disc(path(pos[1]));
      Archive archive(disc);
      result = inspect(disc, archive, expected, job);
    } else if (pos[0] == "extract-xex") {
      require(pos.size() == 3, "Usage: extract-xex ISO OUTPUT.xex");
      Disc disc(path(pos[1]));
      Archive archive(disc);
      result = inspect(disc, archive, expected, job);
      auto output = fs::absolute(path(pos[2]));
      if (fs::exists(output)) {
        require(file_sha(output) == expected,
                "Existing XEX differs; it was left untouched");
      } else {
        write(output, disc.member("default.xex", 0, disc.size("default.xex")));
      }
      result["xex"] = utf8(output);
    } else if (pos[0] == "import") {
      require(pos.size() == 3, "Usage: import ISO NEW_FOLDER");
      result = import_game(path(pos[1]), path(pos[2]), job, expected);
    } else if (pos[0] == "prepare") {
      require(pos.size() == 2, "Usage: prepare GAME_FOLDER");
      result = prepare(path(pos[1]), job);
    } else
      throw std::runtime_error("Unknown native asset tool command");
    std::cout << result.dump(-1, ' ', true) << "\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << "\n";
    return 1;
  }
}
