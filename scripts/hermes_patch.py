#!/usr/bin/env python3
"""Safe installer and credential helper for the versioned Hermes patch.

This utility never downloads a mutable patch, never writes OAuth tokens to
disk, and never edits a profile unless ``configure-profile`` is requested.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence


TOKEN_RE = re.compile(r"sk-ant-oat[^\s'\"`]+")
PROFILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
TOKEN_ENV_KEYS = (
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_TOKEN",
)
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "patches" / "manifest.json"


class InstallerError(RuntimeError):
    """Expected, user-actionable installer failure."""


@dataclass(frozen=True)
class PatchEntry:
    hermes_version: str
    upstream_commit: str
    patch: Path
    sha256: str


@dataclass(frozen=True)
class PatchStatus:
    state: str
    head: str
    entry: PatchEntry
    overlapping_files: tuple[str, ...]


def _run(
    args: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
    input_text: Optional[str] = None,
    timeout: int = 30,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=check,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest(path: Path = DEFAULT_MANIFEST) -> list[PatchEntry]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallerError(f"Cannot read patch manifest: {path}") from exc
    if not isinstance(payload, dict):
        raise InstallerError("Patch manifest root must be an object")
    if payload.get("schema_version") != 1:
        raise InstallerError("Unsupported patch manifest schema")
    entries: list[PatchEntry] = []
    for raw in payload.get("patches", []):
        try:
            patch = (path.parent / str(raw["patch"])).resolve()
            entries.append(
                PatchEntry(
                    hermes_version=str(raw["hermes_version"]),
                    upstream_commit=str(raw["upstream_commit"]),
                    patch=patch,
                    sha256=str(raw["sha256"]),
                )
            )
        except (KeyError, TypeError) as exc:
            raise InstallerError("Malformed patch manifest entry") from exc
    if not entries:
        raise InstallerError("Patch manifest contains no supported versions")
    return entries


def _resolve_checkout(raw: Optional[str]) -> Path:
    candidate = raw or os.environ.get("HERMES_AGENT_DIR")
    if candidate:
        return Path(candidate).expanduser().resolve()
    return (Path.home() / ".hermes" / "hermes-agent").resolve()


def _resolve_hermes_home(raw: Optional[str]) -> Path:
    return (
        Path(raw or os.environ.get("HERMES_HOME") or "~/.hermes").expanduser().resolve()
    )


def _git(
    checkout: Path, *args: str, timeout: int = 30
) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], cwd=checkout, timeout=timeout)


def _require_checkout(checkout: Path) -> None:
    if not checkout.is_dir():
        raise InstallerError(f"Hermes checkout not found: {checkout}")
    probe = _git(checkout, "rev-parse", "--is-inside-work-tree")
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        raise InstallerError(f"Hermes path is not a Git checkout: {checkout}")


def _head(checkout: Path) -> str:
    result = _git(checkout, "rev-parse", "HEAD")
    if result.returncode != 0:
        raise InstallerError("Cannot determine Hermes upstream commit")
    return result.stdout.strip()


def _entry_for_head(entries: Iterable[PatchEntry], head: str) -> PatchEntry:
    for entry in entries:
        if head == entry.upstream_commit:
            return entry
    short = head[:12] if head else "unknown"
    raise InstallerError(f"Unsupported Hermes base commit: {short}")


def _verify_patch(entry: PatchEntry) -> None:
    if not entry.patch.is_file():
        raise InstallerError(f"Versioned patch missing: {entry.patch}")
    actual = _sha256(entry.patch)
    if actual != entry.sha256:
        raise InstallerError(
            "Patch SHA-256 mismatch; refusing to apply "
            f"(expected {entry.sha256}, got {actual})"
        )


def _apply_check(checkout: Path, patch: Path, *, reverse: bool = False) -> bool:
    args = ["apply", "--check"]
    if reverse:
        args.append("--reverse")
    args.append(str(patch))
    return _git(checkout, *args).returncode == 0


def _patch_state(checkout: Path, patch: Path) -> str:
    if _apply_check(checkout, patch, reverse=True):
        return "installed"
    if _apply_check(checkout, patch):
        return "available"
    return "incompatible"


def _patch_files(checkout: Path, patch: Path) -> set[str]:
    result = _git(checkout, "apply", "--numstat", str(patch))
    if result.returncode != 0:
        raise InstallerError("Cannot inspect patch file list")
    files: set[str] = set()
    for line in result.stdout.splitlines():
        fields = line.split("\t", 2)
        if len(fields) == 3:
            files.add(fields[2])
    return files


def _changed_files(checkout: Path) -> set[str]:
    commands = (
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    )
    changed: set[str] = set()
    for command in commands:
        result = _git(checkout, *command)
        if result.returncode != 0:
            raise InstallerError("Cannot inspect Hermes working tree")
        changed.update(line for line in result.stdout.splitlines() if line)
    return changed


def inspect_patch(
    checkout: Path,
    *,
    manifest: Path = DEFAULT_MANIFEST,
) -> PatchStatus:
    _require_checkout(checkout)
    entries = _load_manifest(manifest)
    head = _head(checkout)
    entry = _entry_for_head(entries, head)
    _verify_patch(entry)
    state = _patch_state(checkout, entry.patch)
    overlap: tuple[str, ...] = ()
    if state == "available":
        overlap = tuple(
            sorted(_patch_files(checkout, entry.patch) & _changed_files(checkout))
        )
    return PatchStatus(state=state, head=head, entry=entry, overlapping_files=overlap)


def _print_status(status: PatchStatus, checkout: Path) -> None:
    print(f"Hermes checkout: {checkout}")
    print(f"Hermes base:     {status.entry.hermes_version} ({status.head[:12]})")
    print(f"Patch SHA-256:   {status.entry.sha256}")
    print(f"Patch state:     {status.state}")
    print(f"Overlapping:     {len(status.overlapping_files)} file(s)")
    for path in status.overlapping_files:
        print(f"  - {path}")


def cmd_status(args: argparse.Namespace) -> int:
    checkout = _resolve_checkout(args.hermes_dir)
    status = inspect_patch(checkout, manifest=Path(args.manifest).resolve())
    _print_status(status, checkout)
    return 0 if status.state != "incompatible" else 2


def cmd_install(args: argparse.Namespace) -> int:
    checkout = _resolve_checkout(args.hermes_dir)
    status = inspect_patch(checkout, manifest=Path(args.manifest).resolve())
    _print_status(status, checkout)
    if status.state == "installed":
        print("Patch already installed; nothing changed.")
        return 0
    if status.state != "available":
        raise InstallerError("Patch does not apply cleanly to this checkout")
    if status.overlapping_files:
        raise InstallerError(
            "Refusing to overwrite local changes in patch-touched files"
        )
    if args.dry_run:
        print("Dry run: patch can be installed safely.")
        return 0
    result = _git(checkout, "apply", str(status.entry.patch), timeout=60)
    if result.returncode != 0:
        raise InstallerError("git apply failed; checkout may need inspection")
    if not _apply_check(checkout, status.entry.patch, reverse=True):
        raise InstallerError("Post-install reverse check failed")
    print("Patch installed successfully.")
    print("Run `status` or `doctor` to verify; restart active gateways when ready.")
    return 0


def cmd_remove(args: argparse.Namespace) -> int:
    checkout = _resolve_checkout(args.hermes_dir)
    status = inspect_patch(checkout, manifest=Path(args.manifest).resolve())
    _print_status(status, checkout)
    if status.state == "available":
        print("Patch already absent; nothing changed.")
        return 0
    if status.state != "installed":
        raise InstallerError(
            "Patch cannot be reversed cleanly; preserve local work and inspect git diff"
        )
    if args.dry_run:
        print("Dry run: patch can be removed safely.")
        return 0
    result = _git(
        checkout,
        "apply",
        "--reverse",
        str(status.entry.patch),
        timeout=60,
    )
    if result.returncode != 0:
        raise InstallerError(
            "Reverse apply failed; inspect checkout without resetting it"
        )
    if not _apply_check(checkout, status.entry.patch):
        raise InstallerError("Post-remove apply check failed")
    print("Patch removed. Profile metadata and Keychain setup-tokens were preserved.")
    return 0


def _find_python(checkout: Path) -> Optional[Path]:
    candidates = (
        checkout / "venv" / "bin" / "python",
        checkout / ".venv" / "bin" / "python",
        checkout / "venv" / "Scripts" / "python.exe",
        checkout / ".venv" / "Scripts" / "python.exe",
    )
    return next((path for path in candidates if path.is_file()), None)


def cmd_doctor(args: argparse.Namespace) -> int:
    checkout = _resolve_checkout(args.hermes_dir)
    problems: list[str] = []
    warnings: list[str] = []
    try:
        status = inspect_patch(checkout, manifest=Path(args.manifest).resolve())
        _print_status(status, checkout)
        if status.state == "incompatible":
            problems.append("patch is neither cleanly installable nor removable")
    except InstallerError as exc:
        print(f"Patch check:      FAIL — {exc}")
        problems.append(str(exc))
        status = None

    python = _find_python(checkout)
    print(f"Hermes Python:    {python or 'not found'}")
    if python is None:
        warnings.append("Hermes virtualenv Python not found")

    claude = shutil.which("claude")
    print(f"Claude CLI:       {claude or 'not found'}")
    if claude is None:
        warnings.append("Claude CLI not found; setup-token unavailable")

    if platform.system() == "Darwin":
        compiler = _run(["/usr/bin/xcrun", "--find", "swiftc"], timeout=10)
        swift_ok = compiler.returncode == 0 and bool(compiler.stdout.strip())
        print(f"Swift compiler:   {'available' if swift_ok else 'not found'}")
        if not swift_ok:
            warnings.append(
                "Swift compiler missing; first Keychain helper build will fail"
            )
    else:
        print("Swift compiler:   not required on this platform")

    if args.profile:
        try:
            rows = configured_claude_rows(
                _profile_auth_path(_resolve_hermes_home(args.hermes_home), args.profile)
            )
            print(f"Profile rows:     {len(rows)} config-scoped Claude row(s)")
            if not rows:
                warnings.append("profile has no config-scoped Claude rows")
            elif (
                platform.system() == "Darwin" and status and status.state == "installed"
            ):
                ready, detail = _setup_token_health(rows)
                print(f"Setup-tokens:     {ready}/{len(rows)} valid Keychain item(s)")
                if ready != len(rows):
                    warnings.append(detail)
        except InstallerError as exc:
            problems.append(str(exc))
            print(f"Profile rows:     FAIL — {exc}")

    for warning in warnings:
        print(f"WARNING: {warning}")
    if problems:
        print(f"Doctor result:    FAIL ({len(problems)} problem(s))")
        return 2
    print(f"Doctor result:    OK ({len(warnings)} warning(s))")
    return 0


def _profile_auth_path(hermes_home: Path, profile: str) -> Path:
    if not PROFILE_RE.fullmatch(profile):
        raise InstallerError(
            "Invalid profile name; use letters, numbers, dots, underscores, or hyphens"
        )
    if profile in {"default", "root"}:
        return hermes_home / "auth.json"
    return hermes_home / "profiles" / profile / "auth.json"


def _resolve_config_dir(raw: Any) -> Path:
    path = Path(os.path.expandvars(str(raw))).expanduser()
    try:
        return path.resolve(strict=False)
    except OSError:
        return path.absolute()


def _portable_home_path(path: Path) -> str:
    resolved = _resolve_config_dir(path)
    try:
        relative = resolved.relative_to(Path.home().resolve())
    except ValueError:
        return str(resolved)
    return "~" if str(relative) == "." else f"~/{relative}"


def _source_for_config_dir(path: Path) -> str:
    resolved = _resolve_config_dir(path)
    if resolved == _resolve_config_dir(Path.home() / ".claude"):
        return "claude_code"
    suffix = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:8]
    return f"claude_code:{suffix}"


def configured_claude_rows(auth_path: Path) -> list[dict[str, Any]]:
    try:
        document = json.loads(auth_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InstallerError(f"Profile auth file not found: {auth_path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallerError(
            f"Cannot read valid profile auth JSON: {auth_path}"
        ) from exc
    if not isinstance(document, dict):
        raise InstallerError("Profile auth root must be an object")
    credential_pool = document.get("credential_pool", {})
    if not isinstance(credential_pool, dict):
        raise InstallerError("credential_pool must be an object")
    pool = credential_pool.get("anthropic", [])
    if not isinstance(pool, list):
        raise InstallerError("credential_pool.anthropic must be a list")
    rows = [
        row
        for row in pool
        if isinstance(row, dict)
        and str(row.get("source", "")).startswith("claude_code")
        and (row.get("claude_config_dir") or row.get("CLAUDE_CONFIG_DIR"))
    ]

    def priority(row: dict[str, Any]) -> int:
        try:
            return int(row.get("priority", 999))
        except (TypeError, ValueError):
            return 999

    rows.sort(key=priority)
    return rows


def _setup_token_health(rows: Sequence[dict[str, Any]]) -> tuple[int, str]:
    """Count valid setup-token items without printing or persisting secrets.

    This intentionally does not import the patched adapter: importing it could
    compile the Keychain helper, while ``doctor`` must remain read-only.
    """
    helper = Path.home() / ".hermes" / "runtime-tools" / "hermes-keychain-helper"
    if not helper.is_file() or not os.access(helper, os.X_OK):
        return 0, "Keychain helper missing; run setup-tokens"
    ready = 0
    for row in rows:
        raw = row.get("claude_config_dir") or row.get("CLAUDE_CONFIG_DIR")
        resolved = _resolve_config_dir(raw)
        suffix = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:8]
        service = f"Hermes Claude Code setup-token-v2-{suffix}"
        environment = os.environ.copy()
        environment["HERMES_KEYCHAIN_SERVICE"] = service
        try:
            result = _run([str(helper), "read"], env=environment, timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode != 0 or not result.stdout.strip():
            continue
        try:
            payload = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            continue
        token = str(payload.get("accessToken") or "")
        try:
            expiry = int(payload.get("expiresAt") or 0)
        except (TypeError, ValueError):
            continue
        if (
            payload.get("kind") == "claude_setup_token"
            and token.startswith("sk-ant-oat")
            and expiry > int(time.time() * 1000)
        ):
            ready += 1
    return ready, "one or more setup-tokens are absent, unreadable, or expired"


def _backup_auth(auth_path: Path, hermes_home: Path, profile: str) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = (
        hermes_home
        / "backups"
        / "claude-patch-installer"
        / timestamp
        / ("root" if profile in {"default", "root"} else profile)
        / "auth.json"
    )
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=False)
    shutil.copy2(auth_path, destination)
    destination.chmod(0o600)
    return destination


def _atomic_json_write(path: Path, document: dict[str, Any]) -> None:
    original_mode = stat.S_IMODE(path.stat().st_mode)
    encoded = (json.dumps(document, indent=2, ensure_ascii=False) + "\n").encode()
    fd, temporary_raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary = Path(temporary_raw)
    try:
        os.fchmod(fd, original_mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _updated_profile_document(
    document: dict[str, Any],
    directories: Sequence[Path],
    labels: Sequence[str],
) -> dict[str, Any]:
    credential_pool = document.setdefault("credential_pool", {})
    if not isinstance(credential_pool, dict):
        raise InstallerError("credential_pool must be an object")
    pool = credential_pool.setdefault("anthropic", [])
    if not isinstance(pool, list):
        raise InstallerError("credential_pool.anthropic must be a list")

    for priority, (directory, label) in enumerate(zip(directories, labels)):
        resolved = _resolve_config_dir(directory)
        suffix = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:8]
        matching = None
        for row in pool:
            if not isinstance(row, dict):
                continue
            raw = row.get("claude_config_dir") or row.get("CLAUDE_CONFIG_DIR")
            if raw and _resolve_config_dir(raw) == resolved:
                matching = row
                break
        if matching is None:
            matching = {"id": f"claude-code-{suffix}"}
            pool.append(matching)
        matching.update(
            {
                "label": label,
                "auth_type": "oauth",
                "priority": priority,
                "source": _source_for_config_dir(resolved),
                "claude_config_dir": _portable_home_path(resolved),
            }
        )
        matching.pop("CLAUDE_CONFIG_DIR", None)
        matching.pop("access_token", None)
        matching.pop("refresh_token", None)
    return document


def cmd_configure_profile(args: argparse.Namespace) -> int:
    hermes_home = _resolve_hermes_home(args.hermes_home)
    auth_path = _profile_auth_path(hermes_home, args.profile)
    try:
        document = json.loads(auth_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InstallerError(f"Profile auth file not found: {auth_path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallerError(
            f"Cannot read valid profile auth JSON: {auth_path}"
        ) from exc
    if not isinstance(document, dict):
        raise InstallerError("Profile auth root must be an object")

    directories = [_resolve_config_dir(raw) for raw in args.claude_dir]
    if len(set(directories)) != len(directories):
        raise InstallerError("Duplicate Claude config directory")
    missing = [path for path in directories if not path.is_dir()]
    if missing:
        raise InstallerError(f"Claude config directory not found: {missing[0]}")
    labels = list(args.label or [])
    if labels and len(labels) != len(directories):
        raise InstallerError("Provide one --label for every --claude-dir")
    if not labels:
        labels = [
            "claude-default" if path.name == ".claude" else path.name.lstrip(".")
            for path in directories
        ]
    if any(not label.strip() for label in labels):
        raise InstallerError("Profile labels cannot be empty")

    updated = _updated_profile_document(document, directories, labels)
    print(f"Profile:          {args.profile}")
    print(f"Auth file:        {auth_path}")
    print(f"Claude rows:      {len(directories)}")
    for number, (label, directory) in enumerate(zip(labels, directories), 1):
        print(f"  {number}. {label} -> {_portable_home_path(directory)}")
    if args.dry_run:
        print("Dry run: profile JSON was not changed.")
        return 0
    if not args.yes:
        answer = (
            input("Write metadata-only rows and create backup? [y/N] ").strip().lower()
        )
        if answer not in {"y", "yes"}:
            print("Cancelled; profile unchanged.")
            return 1
    backup = _backup_auth(auth_path, hermes_home, args.profile)
    _atomic_json_write(auth_path, updated)
    print(f"Profile configured. Backup: {backup}")
    print("No OAuth token was written to auth.json.")
    return 0


def _clear_terminal_and_clipboard(token: str) -> None:
    if platform.system() == "Darwin":
        try:
            clipboard = _run(["pbpaste"], timeout=2).stdout.strip()
            if clipboard == token:
                _run(["pbcopy"], input_text="", timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass
    if sys.stdout.isatty():
        print("\033[3J\033[2J\033[H", end="", flush=True)


def _load_setup_token_adapter(checkout: Path):
    if str(checkout) not in sys.path:
        sys.path.insert(0, str(checkout))
    try:
        from agent.anthropic_adapter import (  # type: ignore
            read_claude_code_setup_token,
            store_claude_code_setup_token,
        )
    except Exception as exc:
        raise InstallerError("Cannot load patched Hermes setup-token adapter") from exc
    return read_claude_code_setup_token, store_claude_code_setup_token


def _select_setup_rows(
    rows: Sequence[dict[str, Any]], args: argparse.Namespace
) -> list[dict[str, Any]]:
    if args.all:
        return list(rows)
    if args.slot:
        selected: list[dict[str, Any]] = []
        for slot in args.slot:
            if slot < 1 or slot > len(rows):
                raise InstallerError(f"Slot out of range: {slot}")
            if rows[slot - 1] not in selected:
                selected.append(rows[slot - 1])
        return selected
    print("Configured Claude accounts:")
    for number, row in enumerate(rows, 1):
        raw = row.get("claude_config_dir") or row.get("CLAUDE_CONFIG_DIR")
        print(f"  {number}. {row.get('label') or 'unnamed'} -> {raw}")
    raw_choice = input("Select slot number: ").strip()
    try:
        choice = int(raw_choice)
    except ValueError as exc:
        raise InstallerError("Invalid slot number") from exc
    if choice < 1 or choice > len(rows):
        raise InstallerError("Slot out of range")
    return [rows[choice - 1]]


def cmd_setup_tokens(args: argparse.Namespace) -> int:
    if platform.system() != "Darwin":
        raise InstallerError(
            "setup-token Keychain installation currently requires macOS"
        )
    checkout = _resolve_checkout(args.hermes_dir)
    status = inspect_patch(checkout, manifest=Path(args.manifest).resolve())
    if status.state != "installed":
        raise InstallerError("Install the patch before storing setup-tokens")
    claude = shutil.which("claude")
    if not claude:
        raise InstallerError("Claude CLI not found in PATH")
    auth_path = _profile_auth_path(_resolve_hermes_home(args.hermes_home), args.profile)
    rows = configured_claude_rows(auth_path)
    if not rows:
        raise InstallerError("Profile has no config-scoped Claude rows")
    selected = _select_setup_rows(rows, args)
    read_token, store_token = _load_setup_token_adapter(checkout)

    for index, row in enumerate(selected, 1):
        raw_dir = row.get("claude_config_dir") or row.get("CLAUDE_CONFIG_DIR")
        config_dir = _resolve_config_dir(raw_dir)
        label = str(row.get("label") or config_dir.name)
        print()
        print(f"ACCOUNT {index}/{len(selected)}: {label}")
        print(f"Config directory: {_portable_home_path(config_dir)}")
        hint = input(
            "Browser account hint (display only, not stored; optional): "
        ).strip()
        if hint:
            print(f"In the browser, authenticate as: {hint}")
        answer = (
            input("Start official `claude setup-token` flow? [y/N] ").strip().lower()
        )
        if answer not in {"y", "yes"}:
            print(f"Skipped: {label}")
            continue
        environment = os.environ.copy()
        environment["CLAUDE_CONFIG_DIR"] = str(config_dir)
        for key in TOKEN_ENV_KEYS:
            environment.pop(key, None)
        flow = subprocess.run([claude, "setup-token"], env=environment)
        if flow.returncode != 0:
            raise InstallerError(f"Claude setup-token failed for {label}")
        pasted = getpass.getpass(f"Paste setup-token for {label} (hidden): ").strip()
        match = TOKEN_RE.search(pasted)
        token = match.group(0) if match else ""
        _clear_terminal_and_clipboard(token)
        if not token:
            raise InstallerError(f"Invalid setup-token format for {label}")
        expiry = store_token(token, config_dir)
        stored = read_token(config_dir)
        if not stored or stored.get("accessToken") != token:
            raise InstallerError(f"Keychain round-trip failed for {label}")
        expires = datetime.fromtimestamp(expiry / 1000).astimezone()
        print(f"Stored: {label}; expires {expires:%Y-%m-%d %H:%M %Z}")
    print("Setup-token workflow complete. No inference request was made.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install and manage the versioned Hermes Claude runtime patch."
    )
    parser.add_argument(
        "--hermes-dir",
        help="Hermes Git checkout (default: HERMES_AGENT_DIR or ~/.hermes/hermes-agent)",
    )
    parser.add_argument(
        "--hermes-home",
        help="Hermes data root (default: HERMES_HOME or ~/.hermes)",
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help=argparse.SUPPRESS,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    status = subparsers.add_parser("status", help="Show compatibility and patch state")
    status.set_defaults(func=cmd_status)

    doctor = subparsers.add_parser("doctor", help="Run read-only safety checks")
    doctor.add_argument("--profile", help="Also inspect one Hermes profile")
    doctor.set_defaults(func=cmd_doctor)

    install = subparsers.add_parser(
        "install", help="Apply the matching versioned patch"
    )
    install.add_argument("--dry-run", action="store_true")
    install.set_defaults(func=cmd_install)

    remove = subparsers.add_parser("remove", help="Reverse only this versioned patch")
    remove.add_argument("--dry-run", action="store_true")
    remove.set_defaults(func=cmd_remove)

    configure = subparsers.add_parser(
        "configure-profile",
        help="Add metadata-only Claude config rows to one profile",
    )
    configure.add_argument("--profile", required=True)
    configure.add_argument("--claude-dir", action="append", required=True)
    configure.add_argument("--label", action="append")
    configure.add_argument("--yes", action="store_true")
    configure.add_argument("--dry-run", action="store_true")
    configure.set_defaults(func=cmd_configure_profile)

    setup = subparsers.add_parser(
        "setup-tokens",
        help="Run official setup-token and store tokens in scoped Keychain items",
    )
    setup.add_argument("--profile", required=True)
    selection = setup.add_mutually_exclusive_group()
    selection.add_argument("--slot", action="append", type=int)
    selection.add_argument("--all", action="store_true")
    setup.set_defaults(func=cmd_setup_tokens)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except InstallerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
