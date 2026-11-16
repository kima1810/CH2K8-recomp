#include "crash_report.h"

#include <windows.h>
#include <dbghelp.h>

#include <csignal>

namespace {
// Resolve the output path before a fault so the exception filter need not
// allocate memory or call the runtime logger.
wchar_t dump_path[32768];
LONG reporting;

LONG WINAPI WriteCrashDump(EXCEPTION_POINTERS* exception) {
  if (InterlockedExchange(&reporting, 1) != 0) {
    return EXCEPTION_CONTINUE_SEARCH;
  }

  HANDLE file = CreateFileW(dump_path, GENERIC_WRITE, 0, nullptr, CREATE_NEW,
                            FILE_ATTRIBUTE_NORMAL, nullptr);
  if (file != INVALID_HANDLE_VALUE) {
    MINIDUMP_EXCEPTION_INFORMATION fault{};
    fault.ThreadId = GetCurrentThreadId();
    fault.ExceptionPointers = exception;
    fault.ClientPointers = FALSE;
    const auto type = static_cast<MINIDUMP_TYPE>(
        MiniDumpWithThreadInfo | MiniDumpWithUnloadedModules);
    const BOOL written = MiniDumpWriteDump(GetCurrentProcess(),
                                           GetCurrentProcessId(), file, type,
                                           &fault, nullptr, nullptr);
    CloseHandle(file);
    if (!written) {
      DeleteFileW(dump_path);
    }
  }
  return EXCEPTION_CONTINUE_SEARCH;
}

void WriteAbortDump(int) {
  CONTEXT context{};
  RtlCaptureContext(&context);
  EXCEPTION_RECORD record{};
  // Application-defined exception code for the CRT's SIGABRT.
  record.ExceptionCode = 0xe0420006;
  record.ExceptionFlags = EXCEPTION_NONCONTINUABLE;
#if defined(_M_X64)
  record.ExceptionAddress = reinterpret_cast<void*>(context.Rip);
#elif defined(_M_ARM64)
  record.ExceptionAddress = reinterpret_cast<void*>(context.Pc);
#endif
  EXCEPTION_POINTERS fault{&record, &context};
  WriteCrashDump(&fault);
  // Returning lets the CRT finish the original abort.
}
}  // namespace

void Ch2k8InstallCrashReporter() {
  const DWORD length = GetEnvironmentVariableW(
      L"CH2K8_CRASH_DUMP", dump_path, ARRAYSIZE(dump_path));
  if (length != 0 && length < ARRAYSIZE(dump_path)) {
    SetUnhandledExceptionFilter(WriteCrashDump);
    std::signal(SIGABRT, WriteAbortDump);
  }
}
