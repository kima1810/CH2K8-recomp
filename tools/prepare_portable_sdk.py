"""Make the pinned runtime log sink preserve Unicode Windows paths."""
from pathlib import Path

SINK = r"""
// CH2K8: filesystem paths retain UTF-16 on Windows; narrow fopen corrupts UTF-8.
class Ch2k8PathFileSink final : public spdlog::sinks::base_sink<std::mutex> {
 public:
  explicit Ch2k8PathFileSink(const std::filesystem::path& path)
      : stream_(path, std::ios::out | std::ios::app | std::ios::binary) {
    if (!stream_) throw spdlog::spdlog_ex("Could not open the runtime log file");
  }
 protected:
  void sink_it_(const spdlog::details::log_msg& message) override {
    spdlog::memory_buf_t formatted;
    formatter_->format(message, formatted);
    stream_.write(formatted.data(), static_cast<std::streamsize>(formatted.size()));
    if (!stream_) throw spdlog::spdlog_ex("Could not write the runtime log file");
  }
  void flush_() override { stream_.flush(); }
 private:
  std::ofstream stream_;
};

"""


def prepare_portable(source):
    path = Path(source)/'src/core/logging.cpp'
    text = path.read_text(encoding='utf-8')
    marker = 'std::vector<LogCategoryEntry> g_registry;'
    if 'class Ch2k8PathFileSink final' not in text:
        original = 'std::make_shared<spdlog::sinks::basic_file_sink_mt>(resolved_path.string(), false)'
        if text.count(original) != 1 or text.count(marker) != 1:
            raise ValueError('Unrecognized pinned runtime logging sink')
        text = text.replace('#include <filesystem>', '#include <filesystem>\n#include <fstream>')
        text = text.replace('#include <spdlog/sinks/basic_file_sink.h>', '#include <spdlog/sinks/base_sink.h>')
        text = text.replace(marker, SINK+marker)
        text = text.replace(original, 'std::make_shared<Ch2k8PathFileSink>(resolved_path)')
    original = 'config.log_file = std::string(REXCVAR_GET(log_file));'
    corrected = 'config.log_file = std::filesystem::u8path(std::string(REXCVAR_GET(log_file)));'
    if original in text: text = text.replace(original, corrected)
    elif corrected not in text: raise ValueError('Unrecognized runtime log path override')
    if text != path.read_text(encoding='utf-8'):
        path.write_text(text, encoding='utf-8', newline='\n')

    app = Path(source)/'src/ui/rex_app.cpp'
    text = app.read_text(encoding='utf-8')
    for name in ('game', 'user', 'update'):
        original = f'{name}_dir = {name}_data_cvar;'
        corrected = f'{name}_dir = std::filesystem::u8path({name}_data_cvar);'
        if original in text: text = text.replace(original, corrected)
        elif corrected not in text: raise ValueError(f'Unrecognized {name} data path override')
    if text != app.read_text(encoding='utf-8'):
        app.write_text(text, encoding='utf-8', newline='\n')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    prepare_portable(parser.parse_args().source)
