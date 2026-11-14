"""The only code in the project that downloads model files. Nothing else can: workers run with HF_HUB_OFFLINE=1.

`fetch_weights` downloads exactly the files named in the model registry from the official Hugging Face repositories, in a
throwaway environment that has only huggingface_hub, and records the revision, sizes and SHA-256 of every file in
config/forecast_models.lock.json. `verify` checks that lock before any worker runs, so a swapped or truncated file is caught.
`fetch_code` clones the Kronos source into models/ and records the commit; it never imports or runs it, so it can be read first.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from .. import config
from ..obs.events import emit, utcnow
from .models import SPECS, load_lock, lock_path

KRONOS_REPO = "https://github.com/shiyu-coder/Kronos"

_SNIPPET = """
import json, sys, hashlib, os
from huggingface_hub import snapshot_download
repo, allow = sys.argv[1], json.loads(sys.argv[2])
path = snapshot_download(repo_id=repo, allow_patterns=allow)
files = []
for root, _, names in os.walk(path):
    for n in sorted(names):
        p = os.path.join(root, n)
        h = hashlib.sha256()
        with open(os.path.realpath(p), 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''):
                h.update(chunk)
        files.append({'name': os.path.relpath(p, path), 'size': os.path.getsize(os.path.realpath(p)), 'sha256': h.hexdigest()})
print('RESULT' + json.dumps({'path': path, 'revision': os.path.basename(path), 'files': files}))
"""


def file_entry(path: Path) -> dict:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return {"size": path.stat().st_size, "sha256": h.hexdigest()}


def fetch_weights(name: str) -> dict:
    spec = SPECS[name]
    lock = load_lock()
    entry = {"fetched_at": utcnow().isoformat(), "repos": {}}
    for r in spec.repos:
        proc = subprocess.run(["uv", "run", "--no-project", "--python", "3.13", "--with", "huggingface_hub", "python", "-I", "-c", _SNIPPET, r["repo"], json.dumps(r["allow"])],
                              capture_output=True, text=True, timeout=4 * 3600)
        line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("RESULT")), None)
        if proc.returncode != 0 or line is None:
            raise RuntimeError(f"download of {r['repo']} failed: {(proc.stderr or proc.stdout)[-500:]}")
        entry["repos"][r["repo"]] = json.loads(line[len("RESULT"):])
        emit("forecast.weights_fetched", service="forecast", model=name, repo=r["repo"], files=len(entry["repos"][r["repo"]]["files"]))
    lock[name] = entry
    lock_path().parent.mkdir(exist_ok=True)
    lock_path().write_text(json.dumps(lock, indent=1))
    return entry


def verify(name: str) -> list[str]:
    """Problems with the downloaded weights (empty list means fine): not fetched, missing file, wrong size or hash."""
    lock = load_lock().get(name)
    if not lock:
        return [f"{name} weights are not fetched: run `getrich forecast-fetch {name}`"]
    problems = []
    for repo, info in lock["repos"].items():
        base = Path(info["path"])
        for f in info["files"]:
            p = base / f["name"]
            if not p.exists():
                problems.append(f"{repo}/{f['name']} is missing")
            elif file_entry(p)["sha256"] != f["sha256"]:
                problems.append(f"{repo}/{f['name']} does not match the recorded hash")
    return problems


def verify_code() -> list[str]:
    """The Kronos files that were reviewed must be byte-identical to what will run. Returns problems (empty means fine)."""
    info = load_lock().get("kronos_code")
    if not info or not info.get("reviewed"):
        return ["the Kronos source has not been fetched and reviewed (forecast-fetch-code, read model/*.py, then record the review in config/forecast_models.lock.json)"]
    base = config.root() / "models" / "kronos-src"
    problems = []
    for name, digest in (info.get("reviewed_files") or {}).items():
        p = base / name
        if not p.exists():
            problems.append(f"reviewed file {name} is missing")
        elif file_entry(p)["sha256"] != digest:
            problems.append(f"{name} changed since it was reviewed: read it again before running")
    if not info.get("reviewed_files"):
        problems.append("the review recorded no file hashes")
    return problems


def fetch_code(dest: Path | None = None) -> dict:
    dest = dest or config.root() / "models" / "kronos-src"
    if dest.exists():
        raise RuntimeError(f"{dest} already exists; review it, or delete it to fetch again")
    dest.parent.mkdir(exist_ok=True)
    subprocess.run(["git", "clone", "--depth", "1", KRONOS_REPO, str(dest)], check=True, capture_output=True, text=True, timeout=900)
    sha = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    py = sorted(str(p.relative_to(dest)) for p in dest.rglob("*.py"))
    lock = load_lock()
    lock["kronos_code"] = {"repo": KRONOS_REPO, "commit": sha, "python_files": py, "reviewed": False, "fetched_at": utcnow().isoformat()}
    lock_path().write_text(json.dumps(lock, indent=1))
    emit("forecast.code_fetched", service="forecast", repo=KRONOS_REPO, commit=sha, python_files=len(py))
    return lock["kronos_code"]
