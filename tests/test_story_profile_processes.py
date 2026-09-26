"""Cross-process Profile receipt: API writes, Gateway workers authorize, A→B→A holds.

Each worker is a real subprocess running tests/story_profile_probe.py against a
temp HOME, a temp HERMES_HOME root, two named Profile homes, one shared Vault,
and real copies of this package. Nothing here touches a real Hermes home.
"""

from __future__ import annotations

import collections
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from hermes_env import HERMES

pytestmark = pytest.mark.hermes_integration

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "story-construction"
PROBE_PATH = Path(__file__).resolve().parent / "story_profile_probe.py"
REQUEST_TIMEOUT = 30


def _copy_package(package_root: Path, dest: Path) -> None:
    """Copy the real Story package into one home's plugin folder."""

    (dest / "dashboard").mkdir(parents=True, exist_ok=True)
    shutil.copy(package_root / "plugin.yaml", dest / "plugin.yaml")
    shutil.copy(
        package_root / "dashboard" / "manifest.json",
        dest / "dashboard" / "manifest.json",
    )
    shutil.copy(
        package_root / "dashboard" / "plugin_api.py",
        dest / "dashboard" / "plugin_api.py",
    )
    shutil.copytree(
        package_root / "story_construction_plugin",
        dest / "story_construction_plugin",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        dirs_exist_ok=True,
    )


class _Worker:
    """One probe process speaking JSON lines with finite-timeout requests."""

    def __init__(
        self, proc: subprocess.Popen, role: str, profile: str, timeout: float
    ) -> None:
        self._proc = proc
        self.role = role
        self.profile = profile
        self._timeout = timeout
        self._lines: queue.Queue[str] = queue.Queue()
        self.stderr_tail: collections.deque[str] = collections.deque(maxlen=20)
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()

    @property
    def pid(self) -> int:
        assert self._proc.pid is not None
        return self._proc.pid

    def poll(self) -> int | None:
        return self._proc.poll()

    def _pump_stdout(self) -> None:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            self._lines.put(line)

    def _pump_stderr(self) -> None:
        assert self._proc.stderr is not None
        for line in self._proc.stderr:
            self.stderr_tail.append(line.rstrip("\n"))

    def wait_ready(self) -> dict:
        message = self._next("ready")
        if message.get("code") != "ready":
            raise AssertionError(
                f"{self.role}/{self.profile} did not become ready: {message}; "
                f"stderr tail: {list(self.stderr_tail)}"
            )
        return message

    def request(self, payload: dict) -> dict:
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(payload) + "\n")
        self._proc.stdin.flush()
        return self._next(str(payload.get("op") or "request"))

    def _next(self, label: str) -> dict:
        try:
            line = self._lines.get(timeout=self._timeout)
        except queue.Empty as exc:
            raise AssertionError(
                f"{self.role}/{self.profile} timed out on {label}; "
                f"stderr tail: {list(self.stderr_tail)}"
            ) from exc
        return json.loads(line)

    def stop(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=10)
        for stream in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
            try:
                if stream is not None:
                    stream.close()
            except (OSError, ValueError):
                pass


class _ProfileLab:
    """Temp HOME and HERMES_HOME root, Profiles a/b, one Vault, real package copies."""

    def __init__(self, tmp_path: Path, *, install_default: bool = True) -> None:
        self.tmp_path = tmp_path
        self.home_dir = tmp_path / "home"
        self.root = tmp_path / "hermes"
        self.vault = tmp_path / "vault"
        self.timeout = REQUEST_TIMEOUT
        self._workers: list[_Worker] = []
        self.home_dir.mkdir()
        self.vault.mkdir()
        self.root.mkdir()
        (self.root / "config.yaml").write_text("agent: {}\n", encoding="utf-8")
        for name in ("a", "b"):
            profile_home = self.root / "profiles" / name
            profile_home.mkdir(parents=True)
            # The named Profile's config.yaml doubles as its Hermes identity marker.
            (profile_home / "config.yaml").write_text(
                "plugins:\n"
                "  enabled:\n"
                f"    - {PLUGIN_ID}\n",
                encoding="utf-8",
            )
            _copy_package(PACKAGE_ROOT, profile_home / "plugins" / PLUGIN_ID)
        if install_default:
            self.install_default_copy()

    def install_default_copy(self) -> Path:
        dest = self.root / "plugins" / PLUGIN_ID
        _copy_package(PACKAGE_ROOT, dest)
        return dest

    def start(self, role: str, profile: str) -> _Worker:
        home = self.root if profile == "default" else self.root / "profiles" / profile
        env = os.environ.copy()
        env["HERMES_HOME"] = str(home)
        env["HOME"] = str(self.home_dir)
        env["USERPROFILE"] = str(self.home_dir)
        if HERMES.source is not None:
            env["HERMES_SOURCE"] = str(HERMES.source)
        env["PYTHONIOENCODING"] = "utf-8"
        env.pop("HERMES_MANAGED", None)
        env.pop("HERMES_MANAGED_DIR", None)
        proc = subprocess.Popen(
            [sys.executable, str(PROBE_PATH), role, profile],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
            env=env,
            cwd=str(self.tmp_path),
        )
        worker = _Worker(proc, role, profile, self.timeout)
        self._workers.append(worker)
        worker.wait_ready()
        return worker

    def teardown(self) -> None:
        # Only PIDs this lab started are ever terminated.
        for worker in self._workers:
            worker.stop()


@pytest.fixture
def profile_lab(tmp_path):
    lab = _ProfileLab(tmp_path)
    yield lab
    lab.teardown()


@pytest.fixture
def target_only_lab(tmp_path):
    lab = _ProfileLab(tmp_path, install_default=False)
    yield lab
    lab.teardown()


def test_two_process_bind_unbind_and_a_b_a(profile_lab):
    api = profile_lab.start("api", "default")
    api.request({"op": "select", "profile": "a", "vault_root": str(profile_lab.vault)})
    api.request({"op": "select", "profile": "b"})
    api.request({"op": "select", "profile": "a"})
    agent_a = profile_lab.start("agent", "a")
    agent_b = profile_lab.start("agent", "b")
    assert len({api.pid, agent_a.pid, agent_b.pid}) == 3
    project = api.request({"op": "create", "profile": "a", "name": "Novel"})["tree"][
        "project"
    ]["id"]
    api.request({"op": "bind", "profile": "a", "session_id": "a-1", "project_id": project})
    assert agent_a.request({"op": "tool", "session_id": "a-1", "project_id": project})["ok"]

    # Restart durability after the first bind: fresh processes still authorize.
    api.stop()
    agent_a.stop()
    agent_b.stop()
    api = profile_lab.start("api", "default")
    agent_a = profile_lab.start("agent", "a")
    agent_b = profile_lab.start("agent", "b")
    assert len({api.pid, agent_a.pid, agent_b.pid}) == 3
    assert agent_a.request({"op": "tool", "session_id": "a-1", "project_id": project})["ok"]

    api.request({"op": "select", "profile": "b"})
    assert not agent_b.request({"op": "tool", "session_id": "a-1", "project_id": project})[
        "ok"
    ]
    api.request({"op": "bind", "profile": "b", "session_id": "b-1", "project_id": project})
    assert agent_b.request({"op": "tool", "session_id": "b-1", "project_id": project})["ok"]
    api.request({"op": "select", "profile": "a"})
    api.request({"op": "unbind", "profile": "a", "session_id": "a-1", "project_id": project})
    assert not agent_a.request({"op": "tool", "session_id": "a-1", "project_id": project})[
        "ok"
    ]

    # Restart durability after the unbind: fresh processes still deny.
    agent_a.stop()
    agent_a = profile_lab.start("agent", "a")
    assert not agent_a.request({"op": "tool", "session_id": "a-1", "project_id": project})[
        "ok"
    ]
    assert agent_a.poll() is None


def test_concurrent_api_writers_keep_both_bindings(profile_lab):
    setup = profile_lab.start("api", "default")
    setup.request({"op": "select", "profile": "a", "vault_root": str(profile_lab.vault)})
    project = setup.request({"op": "create", "profile": "a", "name": "Novel"})["tree"][
        "project"
    ]["id"]

    writer_1 = profile_lab.start("api", "default")
    writer_2 = profile_lab.start("api", "default")
    assert len({setup.pid, writer_1.pid, writer_2.pid}) == 3

    barrier = threading.Barrier(2)
    results: dict[str, dict] = {}
    errors: dict[str, BaseException] = {}

    def bind(worker: _Worker, key: str, session_id: str) -> None:
        try:
            barrier.wait(timeout=REQUEST_TIMEOUT)
            results[key] = worker.request(
                {
                    "op": "bind",
                    "profile": "a",
                    "session_id": session_id,
                    "project_id": project,
                }
            )
        except BaseException as exc:  # noqa: BLE001  surfaced on the main thread below
            errors[key] = exc

    threads = [
        threading.Thread(target=bind, args=(writer_1, "w1", "w-1")),
        threading.Thread(target=bind, args=(writer_2, "w2", "w-2")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=REQUEST_TIMEOUT + 5)
    assert not errors, errors
    assert results["w1"]["ok"], results
    assert results["w2"]["ok"], results

    # Both rows survived the concurrent read-modify-write and authorize tools.
    agent = profile_lab.start("agent", "a")
    assert agent.request({"op": "tool", "session_id": "w-1", "project_id": project})["ok"]
    assert agent.request({"op": "tool", "session_id": "w-2", "project_id": project})["ok"]


def test_dashboard_discovery_requires_the_default_install(target_only_lab, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(target_only_lab.root))
    monkeypatch.delenv("HERMES_MANAGED", raising=False)
    monkeypatch.delenv("HERMES_MANAGED_DIR", raising=False)
    from hermes_cli.web_server_dashboard import _discover_dashboard_plugins

    def story_api_entries():
        return [
            entry
            for entry in _discover_dashboard_plugins()
            if entry.get("name") == PLUGIN_ID and entry.get("has_api")
        ]

    # Named-Profile copies alone never surface a Dashboard API entry.
    assert story_api_entries() == []

    target_only_lab.install_default_copy()

    found = story_api_entries()
    assert len(found) == 1
    assert found[0]["_api_file"] == "plugin_api.py"
