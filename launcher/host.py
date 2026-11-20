"""CH2K8 / CHRB2K launcher host.

Serves launcher/index.html on 127.0.0.1 and opens it in an app-style window.
The page calls a small JSON API here to read and save settings, manage mods and
start the game. Starting the game still goes through tools/launch_ch2k8.ps1 -Launch,
so the game arguments are exactly the ones the classic launcher uses.

Standard library only. Run:  python -B launcher/host.py   (or Launch CH2K8.cmd)
Add --no-open to skip opening a window, --port N to pick a port.
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
USERDATA = REPO / "port" / "userdata"
SETTINGS_FILE = USERDATA / "launcher.json"          # same file and keys as the classic launcher
MODS_FILE = USERDATA / "launcher-mods.json"          # new: mod on/off + what is applied
LAUNCH_PS1 = REPO / "tools" / "launch_ch2k8.ps1"
IS_WIN = sys.platform == "win32"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

RENDERERS = ("d3d12", "vulkan")
RENDER_PATHS = ("auto", "native", "accurate")
RESOLUTIONS = ("1280x720", "1600x900", "1920x1080", "2560x1440", "3840x2160")
WINDOW_MODES = ("windowed", "borderless", "exclusive")
DEFAULTS = {"renderer": "d3d12", "render_path": "auto", "resolution": "1280x720",
            "refresh_rate": 60, "window_mode": "windowed", "game_data": ""}
LINKS = {
    "discord": "https://discord.gg/FhBHUdQ9h",
    "recomp": "https://github.com/kima1810/CH2K8-recomp",
    "studio": "https://github.com/ZMO34/CHoops-Extractor-Reborn-Recomp",
}
STATIC = {"/": "index.html", "/index.html": "index.html", "/launcher.css": "launcher.css",
          "/assets/RSN.png": "assets/RSN.png", "/assets/CHRB2K.png": "assets/CHRB2K.png"}
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".png": "image/png"}

TOKEN = secrets.token_urlsafe(24)
LOCK = threading.RLock()
STATE = {"last_ping": None, "port": 0}
JOB = {"state": "idle", "message": "", "steps": [], "current": -1}


# ---------------------------------------------------------------- settings / json
def read_json(path, fallback):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return fallback


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_settings():
    saved = read_json(SETTINGS_FILE, {})
    s = dict(DEFAULTS)
    if saved.get("renderer") in RENDERERS: s["renderer"] = saved["renderer"]
    if saved.get("render_path") in RENDER_PATHS: s["render_path"] = saved["render_path"]
    if saved.get("resolution") in RESOLUTIONS: s["resolution"] = saved["resolution"]
    if isinstance(saved.get("refresh_rate"), int) and 24 <= saved["refresh_rate"] <= 240:
        s["refresh_rate"] = saved["refresh_rate"]
    if saved.get("window_mode") in WINDOW_MODES: s["window_mode"] = saved["window_mode"]
    if isinstance(saved.get("game_data"), str): s["game_data"] = saved["game_data"]
    return s, saved


def save_settings(changes):
    s, saved = load_settings()
    for key, value in changes.items():
        if key == "renderer" and value in RENDERERS: s[key] = value
        elif key == "render_path" and value in RENDER_PATHS: s[key] = value
        elif key == "resolution" and value in RESOLUTIONS: s[key] = value
        elif key == "window_mode" and value in WINDOW_MODES: s[key] = value
        elif key == "refresh_rate":
            value = int(value)
            if not 24 <= value <= 240: raise ValueError("Refresh rate must be 24-240 Hz.")
            s[key] = value
        elif key == "game_data":
            value = str(value).strip()
            if '"' in value: raise ValueError("Paths must not contain double quotes.")
            s[key] = value
    merged = dict(saved)      # keep keys the classic launcher wrote (e.g. executable)
    merged.update(s)
    write_json(SETTINGS_FILE, merged)
    return s


def default_game_data():
    if (REPO / "default.xex").is_file(): return REPO
    if (REPO / "game" / "default.xex").is_file(): return REPO / "game"
    return REPO / "work" / "ch2k8" / "XBOX" / "disc"


def effective_game_data(settings):
    if not settings["game_data"]: return default_game_data()
    path = Path(settings["game_data"])
    if (path / "default.xex").is_file(): return path
    # Older settings point at CH2KRB\game; the data now lives in CH2KRB\[Mod]\game (or under the folder given).
    for alt in (path / "[Mod]" / "game", path.parent / "[Mod]" / "game"):
        if (alt / "default.xex").is_file(): return alt
    return path


def find_executable(renderer):
    portable = REPO / "ch2k8.exe"
    dual = REPO / "port" / "out" / "build" / "win-amd64-vulkan" / "ch2k8.exe"
    single = REPO / "port" / "out" / "build" / "win-amd64" / "ch2k8.exe"
    if portable.is_file(): return portable
    return dual if (renderer == "vulkan" or dual.is_file()) else single


# ---------------------------------------------------------------- mods
def mods_dir():
    candidates = [REPO / "mods", REPO.parent / "CH2KRB" / "[Mod]" / "mods"]
    for c in candidates:
        if c.is_dir(): return c
    return None


def parse_readme(path):
    name, desc = None, ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None, ""
    for line in lines:
        if name is None and line.startswith("# "):
            name = line[2:].strip()
            continue
        if name and line.strip() and not line.startswith(("#", "|", "```", "-", "1.", "2.", "3.")):
            desc = line.strip()
            break
    return name, desc


def mod_state():
    return read_json(MODS_FILE, {"enabled": [], "applied": {}})


def list_mods(game_dir):
    root = mods_dir()
    if root is None: return None, []
    st = mod_state()
    items = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        readme, build = d / "README.md", d / "build_mod.py"
        if not readme.is_file() and not build.is_file(): continue
        name, desc = parse_readme(readme) if readme.is_file() else (None, "")
        items.append({
            "id": d.name, "name": name or d.name, "description": desc,
            "type": "Game edit" if build.is_file() else "No build script",
            "loadable": build.is_file(),
            "enabled": d.name in st["enabled"],
            "applied": st["applied"].get(d.name) == str(game_dir),
        })
    return str(root), items


# ---------------------------------------------------------------- roster / folders
def saved_rosters():
    found = []
    if USERDATA.is_dir():
        base = len(USERDATA.parts)
        for root, dirs, files in os.walk(USERDATA):
            if len(Path(root).parts) - base >= 4: dirs[:] = []
            for f in files:
                if f.lower() == "roster.ros": found.append(str(Path(root) / f))
    return found


def open_path(path):
    path = str(path)
    if IS_WIN: os.startfile(path)                      # noqa: S606 - fixed, known folders only
    elif sys.platform == "darwin": subprocess.Popen(["open", path])
    else: subprocess.Popen(["xdg-open", path])


# ---------------------------------------------------------------- jobs (mods + launch)
def game_running():
    if not IS_WIN: return False
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ch2k8.exe", "/NH"], capture_output=True,
                             text=True, creationflags=NO_WINDOW, timeout=10).stdout
        return "ch2k8.exe" in out.lower()
    except (OSError, subprocess.SubprocessError):
        return False


def powershell_cmd():
    if IS_WIN: return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    return [shutil.which("pwsh") or "pwsh", "-NoProfile"]


def run_step(step):
    proc = subprocess.run(step["cmd"], cwd=step.get("cwd"), capture_output=True, text=True,
                          errors="replace", creationflags=NO_WINDOW, timeout=step.get("timeout", 3600))
    if proc.returncode != 0:
        tail = (proc.stdout + "\n" + proc.stderr).strip()[-1200:]
        raise RuntimeError(f"{step['label']} failed (exit {proc.returncode}).\n{tail}")


def job_thread(steps):
    try:
        for i, step in enumerate(steps):
            with LOCK:
                JOB["current"], JOB["message"] = i, step["label"] + "..."
            run_step(step)
            if "after" in step: step["after"]()
        with LOCK:
            JOB["state"], JOB["message"] = "ok", "Game started."
    except Exception as exc:                                   # shown to the user in the page
        with LOCK:
            JOB["state"], JOB["message"] = "error", str(exc)


def mark_applied(mod_id, game_dir, applied):
    with LOCK:
        st = mod_state()
        if applied: st["applied"][mod_id] = str(game_dir)
        else: st["applied"].pop(mod_id, None)
        write_json(MODS_FILE, st)


def start_play(with_mods):
    with LOCK:
        if JOB["state"] == "running": raise RuntimeError("Already working. Wait for the current step to finish.")
    if game_running(): raise RuntimeError("CH2K8 is already running. Close it first.")
    s, _ = load_settings()
    game_dir = effective_game_data(s)
    if not (game_dir / "default.xex").is_file():
        raise RuntimeError(f"Game data folder has no default.xex: {game_dir}\nSet it in Settings.")
    exe = find_executable(s["renderer"])
    if not exe.is_file(): raise RuntimeError(f"Game build is missing: {exe}")
    if not LAUNCH_PS1.is_file(): raise RuntimeError(f"Missing {LAUNCH_PS1}")

    steps, st = [], mod_state()
    root = mods_dir()
    if root is not None:
        for d in sorted(p for p in root.iterdir() if p.is_dir() and (p / "build_mod.py").is_file()):
            applied = st["applied"].get(d.name) == str(game_dir)
            want = with_mods and d.name in st["enabled"]
            if applied and not want:
                steps.append({"label": f"Removing mod {d.name}", "cwd": str(d.parents[1]),
                              "cmd": [sys.executable, "-B", str(d / "build_mod.py"), "revert", str(game_dir)],
                              "after": (lambda n=d.name: mark_applied(n, game_dir, False))})
            elif want and not applied:
                steps.append({"label": f"Applying mod {d.name}", "cwd": str(d.parents[1]),
                              "cmd": [sys.executable, "-B", str(d / "build_mod.py"), "apply", str(game_dir)],
                              "after": (lambda n=d.name: mark_applied(n, game_dir, True))})
    launch = powershell_cmd() + ["-File", str(LAUNCH_PS1), "-Launch", "-Renderer", s["renderer"],
                                 "-RenderPath", s["render_path"], "-Resolution", s["resolution"],
                                 "-RefreshRate", str(s["refresh_rate"]), "-WindowMode", s["window_mode"]]
    if s["game_data"]: launch += ["-GameData", str(game_dir)]
    steps.append({"label": "Starting the game", "cmd": launch, "cwd": str(REPO), "timeout": 3600})
    with LOCK:
        JOB.update(state="running", message=steps[0]["label"] + "...", steps=[x["label"] for x in steps], current=0)
    threading.Thread(target=job_thread, args=(steps,), daemon=True).start()


# ---------------------------------------------------------------- API
def full_state():
    s, _ = load_settings()
    game_dir = effective_game_data(s)
    exe = find_executable(s["renderer"])
    root, items = list_mods(game_dir)
    with LOCK: job = dict(JOB)
    return {
        "settings": s, "game_data_effective": str(game_dir), "game_data_is_default": not s["game_data"],
        "setup": {"game_data_ok": (game_dir / "default.xex").is_file(), "exe_ok": exe.is_file(), "exe_path": str(exe)},
        "mods": {"dir": root, "items": items},
        "roster": {"files": saved_rosters(), "userdata": str(USERDATA)},
        "job": job, "options": {"resolutions": RESOLUTIONS},
    }


def api_post(path, body):
    if path == "/api/settings":
        save_settings(body); return full_state()
    if path == "/api/mods/toggle":
        mod_id, enabled = str(body.get("id", "")), bool(body.get("enabled"))
        _, items = list_mods(effective_game_data(load_settings()[0]))
        if mod_id not in {m["id"] for m in items if m["loadable"]}: raise ValueError("Unknown or not loadable mod.")
        with LOCK:
            st = mod_state()
            st["enabled"] = [m for m in st["enabled"] if m != mod_id] + ([mod_id] if enabled else [])
            write_json(MODS_FILE, st)
        return full_state()
    if path == "/api/mods/disable_all":
        with LOCK:
            st = mod_state(); st["enabled"] = []; write_json(MODS_FILE, st)
        return full_state()
    if path == "/api/play":
        start_play(bool(body.get("with_mods"))); return full_state()
    if path == "/api/open":
        target = body.get("target")
        if target in LINKS: webbrowser.open(LINKS[target])
        elif target == "mods":
            root = mods_dir()
            if root is None: raise ValueError("No mods folder found.")
            open_path(root)
        elif target == "saves": USERDATA.mkdir(parents=True, exist_ok=True); open_path(USERDATA)
        elif target == "logs":
            logs = find_executable(load_settings()[0]["renderer"]).parent / "logs"
            logs.mkdir(parents=True, exist_ok=True); open_path(logs)
        else: raise ValueError("Unknown target.")
        return {"ok": True}
    if path == "/api/roster/reset":
        stamp, moved = time.strftime("%Y%m%d-%H%M%S"), 0
        for f in saved_rosters():
            os.replace(f, f + f".bak-{stamp}"); moved += 1       # renamed, never deleted
        return {"ok": True, "moved": moved, **full_state()}
    if path == "/api/quit":
        threading.Thread(target=lambda: (time.sleep(0.2), os._exit(0)), daemon=True).start()
        return {"ok": True}
    raise KeyError(path)


class Handler(BaseHTTPRequestHandler):
    server_version = "CH2K8Launcher"

    def log_message(self, *a): pass

    def _host_ok(self):
        return self.headers.get("Host", "") in (f"127.0.0.1:{STATE['port']}", f"localhost:{STATE['port']}")

    def _send(self, code, payload, ctype="application/json; charset=utf-8"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self._host_ok(): return self._send(403, {"error": "bad host"})
        path = self.path.split("?")[0]
        if path in STATIC:
            file = HERE / STATIC[path]
            if not file.is_file(): return self._send(404, {"error": "missing " + STATIC[path]})
            data = file.read_bytes()
            if file.suffix == ".html": data = data.replace(b"__LAUNCHER_TOKEN__", TOKEN.encode())
            return self._send(200, data, MIME[file.suffix])
        if path.startswith("/api/"):
            if self.headers.get("X-Token") != TOKEN: return self._send(403, {"error": "bad token"})
            if path == "/api/state": return self._send(200, full_state())
            if path == "/api/ping":
                STATE["last_ping"] = time.time(); return self._send(200, {"ok": True})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._host_ok() or self.headers.get("X-Token") != TOKEN: return self._send(403, {"error": "forbidden"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            self._send(200, api_post(self.path.split("?")[0], body))
        except KeyError:
            self._send(404, {"error": "not found"})
        except (ValueError, RuntimeError) as exc:
            self._send(400, {"error": str(exc)})
        except Exception as exc:
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})


def open_window(url):
    if IS_WIN:
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
            edge = Path(base or "") / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if base and edge.is_file():
                subprocess.Popen([str(edge), f"--app={url}", "--window-size=1280,800"])
                return
    webbrowser.open(url)


def watchdog():
    """Exit when the page has gone away (no ping for 20 s after the first one)."""
    while True:
        time.sleep(2)
        last = STATE["last_ping"]
        with LOCK: busy = JOB["state"] == "running"
        if last and not busy and time.time() - last > 20: os._exit(0)


def main():
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 0
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    STATE["port"] = server.server_address[1]
    url = f"http://127.0.0.1:{STATE['port']}/"
    if sys.stdout: print("Launcher running at", url, flush=True)
    if "--no-open" not in sys.argv: open_window(url)
    threading.Thread(target=watchdog, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    try:
        main()
    except Exception:                       # pythonw has no console: keep the error somewhere findable
        import tempfile, traceback
        Path(tempfile.gettempdir(), "CH2K8-launcher-host.log").write_text(traceback.format_exc(), encoding="utf-8")
        raise
