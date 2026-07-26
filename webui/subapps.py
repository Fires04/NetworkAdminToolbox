"""subapps.py - discovery + process supervisor for the apps/ modules.

Mirrors the cli_scripts/ auto-discovery convention (drop a file in, it shows
up -- no central registry) for a different module shape: full standalone
web apps (their own framework, own routes) instead of run-and-exit scripts.
Each subfolder of apps/ that has an app.yaml manifest is picked up
automatically and, on first request, started as a child process bound to
127.0.0.1 on its own internal port, then reverse-proxied by app.py under
/app/<name>/ so it appears under the toolbox's own host:port.
"""
import atexit
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APPS_DIR = PROJECT_ROOT / "apps"
LOGS_DIR = PROJECT_ROOT / "logs"
MANIFEST_NAME = "app.yaml"
STARTUP_TIMEOUT = 20


def _load_config():
    """Return {name: {"description", "port", "cmd", "dir"}} for every
    apps/<name>/app.yaml manifest found."""
    apps = {}
    if not APPS_DIR.is_dir():
        return apps
    for entry in sorted(APPS_DIR.iterdir()):
        manifest = entry / MANIFEST_NAME
        if not entry.is_dir() or not manifest.exists():
            continue
        with open(manifest) as f:
            cfg = yaml.safe_load(f) or {}
        cfg["dir"] = entry
        apps[entry.name] = cfg
    return apps


def _port_open(port, timeout=0.5):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


class SubappManager:
    def __init__(self):
        self.subapps = _load_config()
        self._procs = {}
        self._log_files = {}
        atexit.register(self.stop_all)

    def list_subapps(self):
        """Return {name: {"description": ..., "port": ...}} for all discovered apps."""
        return {name: {"description": cfg.get("description", ""), "port": cfg["port"]}
                for name, cfg in self.subapps.items()}

    def is_running(self, name):
        proc = self._procs.get(name)
        return proc is not None and proc.poll() is None

    def ensure_running(self, name):
        """Start the app if it isn't already running. Returns its internal
        port once it's accepting connections, or None if name is unknown."""
        cfg = self.subapps.get(name)
        if cfg is None:
            return None

        port = cfg["port"]
        if self.is_running(name):
            return port
        if _port_open(port):
            # Something's already listening there (e.g. a previous run this
            # process lost track of) -- treat it as good enough.
            return port

        cwd = cfg["dir"]
        cmd = [str(part).format(python=sys.executable, port=port) for part in cfg["cmd"]]
        env = {**os.environ, "PYTHONPATH": str(cwd)}

        LOGS_DIR.mkdir(exist_ok=True)
        log_file = open(LOGS_DIR / f"{name}.log", "a")
        proc = subprocess.Popen(cmd, cwd=cwd, env=env,
                                 stdout=log_file, stderr=subprocess.STDOUT)
        self._procs[name] = proc
        self._log_files[name] = log_file

        deadline = time.time() + STARTUP_TIMEOUT
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"app {name!r} exited early (code {proc.returncode})")
            if _port_open(port):
                return port
            time.sleep(0.2)

        proc.terminate()
        raise RuntimeError(f"app {name!r} did not start within {STARTUP_TIMEOUT}s")

    def stop_all(self):
        for proc in self._procs.values():
            if proc.poll() is None:
                proc.terminate()
        for proc in self._procs.values():
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        for log_file in self._log_files.values():
            log_file.close()
