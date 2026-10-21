"""Manage the statements the pipeline reads: upload, check, add or replace, archive, restore.

Layout on disk (all under data/, all git-ignored):
  raw/       the statements the pipeline analyses, named N_SOA.<ext> (N becomes the account id SOA<N>)
  staging/   uploaded files that passed the checks, waiting for "Run analysis"
  archive/   statements set aside by "replace" or "remove", one folder per event, restorable

Each folder keeps a .manifest.json with the original file name, upload time and
content hash of the files Trace360 stored there. Files from the original dataset
have no manifest entry.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from app import config
from app.ingestion.adapters.base import SourceContext
from app.ingestion.layout_detector import UnknownLayoutError, detect_layout
from app.ingestion.loader import read_sheets

ALLOWED_SUFFIXES = (".xls", ".xlsx", ".csv")
MAX_UPLOAD_MB = 100
MANIFEST = ".manifest.json"
NAME_RE = re.compile(r"^[\w.\-]+$")  # stored file and archive names: no paths


class DatasetError(ValueError):
    """A request the dataset cannot carry out (unknown file, bad name...)."""


def raw_dir() -> Path:
    return config.RAW_DIR


def staging_dir() -> Path:
    return config.RAW_DIR.parent / "staging"


def archive_dir() -> Path:
    return config.RAW_DIR.parent / "archive"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_manifest(folder: Path) -> dict:
    p = folder / MANIFEST
    return json.loads(p.read_text()) if p.exists() else {}


def _write_manifest(folder: Path, data: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / MANIFEST).write_text(json.dumps(data, indent=2))


def _statements(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_SUFFIXES and not p.name.startswith("~$")),
                  key=lambda p: (_file_no(p.name) or 0, p.name))


def _file_no(name: str) -> int | None:
    m = re.match(config.RAW_FILE_PATTERN, name, re.IGNORECASE)
    return int(m.group(1)) if m else None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_name(name: str) -> str:
    if not NAME_RE.match(name) or name.startswith("."):
        raise DatasetError(f"invalid name '{name}'")
    return name


# ---------------------------------------------------------------- checks
def inspect_statement(path: Path, display_name: str | None = None) -> list[dict]:
    """Run each sheet through layout detection and its adapter, as the pipeline would.

    `display_name` names a CSV's single sheet (the stored file has a generated name).
    Raises DatasetError with a readable reason when the file cannot be analysed.
    """
    sheets = []
    try:
        for sheet, df in read_sheets(path):
            if path.suffix.lower() == ".csv" and display_name:
                sheet = Path(display_name).stem
            df.columns = [str(c).strip() for c in df.columns]
            if df.empty:
                continue
            try:
                adapter = detect_layout(df)()
            except UnknownLayoutError:
                raise DatasetError(
                    f"sheet '{sheet}' does not match any supported statement layout "
                    f"(its columns are: {', '.join(list(df.columns)[:12])})"
                ) from None
            t = adapter.to_canonical(df, SourceContext(0, path.name, sheet)).transactions
            reliable = bool(t["time_reliable"].any()) if len(t) else False
            ts = t["txn_ts"].dropna() if reliable else t["txn_ts"].iloc[0:0]
            sheets.append({
                "sheet": sheet, "layout": adapter.name, "n_rows": int(len(t)),
                "first_date": ts.min().date().isoformat() if len(ts) else None,
                "last_date": ts.max().date().isoformat() if len(ts) else None,
                "time_reliable": reliable,
                "pct_counterparty": round(100 * float(t["counterparty_key"].notna().mean()), 1) if len(t) else 0.0,
            })
    except DatasetError:
        raise
    except Exception as e:  # unreadable workbook, bad CSV encoding, ...
        raise DatasetError(f"could not read the file: {e}") from e
    if not sheets or not sum(s["n_rows"] for s in sheets):
        raise DatasetError("the file has no transaction rows")
    return sheets


# ---------------------------------------------------------------- staging
def _known_hashes() -> dict[str, str]:
    """content hash -> where it already is ('the dataset as 7_SOA.xlsx' / 'the upload list')."""
    known = {}
    for p in _statements(raw_dir()):
        known[_sha256(p)] = f"the dataset as {p.name}"
    for meta in _read_manifest(staging_dir()).values():
        known[meta["sha256"]] = "the upload list"
    return known


def stage(filename: str, data: bytes) -> dict:
    """Check an uploaded statement and keep it in staging if it can be analysed.

    Always returns a record; ok=False (and nothing stored) when it is rejected.
    """
    name = Path(filename or "upload").name
    suffix = Path(name).suffix.lower()
    rec = {"id": "", "original_name": name, "size_bytes": len(data), "uploaded_at": _now(), "ok": False, "error": None, "sheets": []}
    if suffix not in ALLOWED_SUFFIXES:
        rec["error"] = f"unsupported file type '{suffix or 'none'}'; upload .xls, .xlsx or .csv bank statements"
        return rec
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        rec["error"] = f"file is larger than {MAX_UPLOAD_MB} MB"
        return rec
    if not data:
        rec["error"] = "the file is empty"
        return rec
    sha = hashlib.sha256(data).hexdigest()
    where = _known_hashes().get(sha)
    if where:
        rec["error"] = f"this file is already in {where}"
        return rec
    folder = staging_dir()
    folder.mkdir(parents=True, exist_ok=True)
    file_id = f"{sha[:12]}{suffix}"
    path = folder / file_id
    path.write_bytes(data)
    try:
        rec["sheets"] = inspect_statement(path, name)
    except DatasetError as e:
        path.unlink(missing_ok=True)
        rec["error"] = str(e)
        return rec
    rec.update(id=file_id, ok=True)
    manifest = _read_manifest(folder)
    manifest[file_id] = {**{k: rec[k] for k in ("original_name", "size_bytes", "uploaded_at", "sheets")}, "sha256": sha}
    _write_manifest(folder, manifest)
    return rec


def staged() -> list[dict]:
    manifest = _read_manifest(staging_dir())
    return [{"id": fid, "ok": True, "error": None, **{k: m[k] for k in ("original_name", "size_bytes", "uploaded_at", "sheets")}}
            for fid, m in manifest.items() if (staging_dir() / fid).exists()]


def unstage(file_id: str) -> None:
    _check_name(file_id)
    manifest = _read_manifest(staging_dir())
    if file_id not in manifest:
        raise DatasetError(f"no uploaded file '{file_id}'")
    (staging_dir() / file_id).unlink(missing_ok=True)
    del manifest[file_id]
    _write_manifest(staging_dir(), manifest)


# ---------------------------------------------------------------- dataset
def current_files() -> list[dict]:
    manifest = _read_manifest(raw_dir())
    out = []
    for p in _statements(raw_dir()):
        m = manifest.get(p.name, {})
        out.append({"name": p.name, "original_name": m.get("original_name"), "uploaded_at": m.get("uploaded_at"),
                    "size_bytes": p.stat().st_size})
    return out


def _used_numbers() -> set[int]:
    used = {_file_no(p.name) for p in _statements(raw_dir())}
    if archive_dir().exists():
        for d in archive_dir().iterdir():
            if d.is_dir():
                used |= {_file_no(p.name) for p in _statements(d)}
    return {n for n in used if n is not None}


def _archive(files: list[Path], reason: str) -> str | None:
    """Move `files` (from raw/) into a new archive folder; returns its name."""
    if not files:
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name, i = f"{stamp}-{reason}", 1
    while (archive_dir() / name).exists():
        i += 1
        name = f"{stamp}-{reason}-{i}"
    dest = archive_dir() / name
    dest.mkdir(parents=True)
    raw_manifest = _read_manifest(raw_dir())
    moved = {}
    for p in files:
        shutil.move(str(p), dest / p.name)
        moved[p.name] = raw_manifest.pop(p.name, {})
    _write_manifest(raw_dir(), raw_manifest)
    _write_manifest(dest, {"__archive__": {"created_at": _now(), "reason": reason}, **moved})
    return name


def remove_file(name: str) -> str:
    _check_name(name)
    path = raw_dir() / name
    if not path.exists() or path not in _statements(raw_dir()):
        raise DatasetError(f"no statement '{name}' in the dataset")
    if len(_statements(raw_dir())) == 1:
        raise DatasetError("this is the only statement left; upload another one or use replace instead")
    return _archive([path], "removed")


def apply_staged(mode: str) -> list[str]:
    """Move staged uploads into raw/. mode='replace' first archives every current statement.

    Each upload is stored as N_SOA.<ext>: its own number if it already has that form and
    the number is free, otherwise the next number never used before (so account ids stay unique).
    """
    if mode not in ("add", "replace"):
        raise DatasetError("mode must be 'add' or 'replace'")
    uploads = staged()
    if mode == "replace":
        if not uploads:
            raise DatasetError("replace needs at least one uploaded file")
        _archive(_statements(raw_dir()), "replaced")
    raw_dir().mkdir(parents=True, exist_ok=True)
    used = _used_numbers()
    staging_manifest = _read_manifest(staging_dir())
    raw_manifest = _read_manifest(raw_dir())
    added = []
    for u in uploads:
        suffix = Path(u["id"]).suffix
        n = _file_no(u["original_name"])
        if n is None or n in used:
            n = max(used, default=0) + 1
        used.add(n)
        target = f"{n}_SOA{suffix}"
        shutil.move(str(staging_dir() / u["id"]), raw_dir() / target)
        raw_manifest[target] = {k: v for k, v in staging_manifest.pop(u["id"]).items() if k != "sheets"}
        added.append(target)
    _write_manifest(raw_dir(), raw_manifest)
    _write_manifest(staging_dir(), staging_manifest)
    return added


def archives() -> list[dict]:
    if not archive_dir().exists():
        return []
    out = []
    for d in sorted((d for d in archive_dir().iterdir() if d.is_dir()), reverse=True):
        manifest = _read_manifest(d)
        info = manifest.get("__archive__", {})
        files = _statements(d)
        if not files:
            continue
        out.append({"name": d.name, "created_at": info.get("created_at"), "reason": info.get("reason", "archived"),
                    "files": [manifest.get(p.name, {}).get("original_name") or p.name for p in files], "n_files": len(files)})
    return out


def restore(name: str) -> None:
    """Put an archived set back as the dataset; the current statements are archived first."""
    _check_name(name)
    src = archive_dir() / name
    files = _statements(src)
    if not src.is_dir() or not files:
        raise DatasetError(f"no archived set '{name}'")
    src_manifest = _read_manifest(src)
    if src_manifest.get("__archive__", {}).get("reason") == "removed":
        # a removed file goes back next to the current statements
        clash = [p.name for p in files if (raw_dir() / p.name).exists()]
        if clash:
            raise DatasetError(f"{', '.join(clash)} is already in the dataset")
    else:
        _archive(_statements(raw_dir()), "replaced")
    raw_dir().mkdir(parents=True, exist_ok=True)
    raw_manifest = _read_manifest(raw_dir())
    for p in files:
        shutil.move(str(p), raw_dir() / p.name)
        if src_manifest.get(p.name):
            raw_manifest[p.name] = src_manifest[p.name]
    _write_manifest(raw_dir(), raw_manifest)
    shutil.rmtree(src)
