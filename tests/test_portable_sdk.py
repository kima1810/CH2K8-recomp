import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from prepare_portable_sdk import prepare_portable


def test_unicode_path_patch_is_idempotent_and_preserves_other_code(tmp_path):
    log = tmp_path/'src/core/logging.cpp'
    log.parent.mkdir(parents=True)
    log.write_text('#include <filesystem>\n#include <spdlog/sinks/basic_file_sink.h>\n'
                   'std::vector<LogCategoryEntry> g_registry;\n'
                   'auto sink = std::make_shared<spdlog::sinks::basic_file_sink_mt>(resolved_path.string(), false);\n'
                   'config.log_file = std::string(REXCVAR_GET(log_file));\n// keep me\n')
    app = tmp_path/'src/ui/rex_app.cpp'
    app.parent.mkdir(parents=True)
    app.write_text('\n'.join(f'{name}_dir = {name}_data_cvar;' for name in ('game','user','update')))
    prepare_portable(tmp_path)
    expected = log.read_bytes(), app.read_bytes()
    prepare_portable(tmp_path)
    assert (log.read_bytes(),app.read_bytes()) == expected
    assert 'Ch2k8PathFileSink' in log.read_text()
    assert '// keep me' in log.read_text()
    assert 'std::filesystem::u8path(user_data_cvar)' in app.read_text()


def test_unicode_patch_refuses_unrecognized_sdk_source(tmp_path):
    log = tmp_path/'src/core/logging.cpp'
    log.parent.mkdir(parents=True)
    log.write_text('unknown logger')
    with pytest.raises(ValueError,match='Unrecognized'):
        prepare_portable(tmp_path)
    assert log.read_text()=='unknown logger'
