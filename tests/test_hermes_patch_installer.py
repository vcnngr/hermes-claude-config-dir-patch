from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.hermes_patch import (
    InstallerError,
    _select_setup_rows,
    configured_claude_rows,
    inspect_patch,
    main,
)


BASE_TEXT = "before\n" + "".join(f"keep-{number}\n" for number in range(1, 11))
PATCHED_TEXT = "after\n" + "".join(f"keep-{number}\n" for number in range(1, 11))


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def synthetic_patch(tmp_path: Path):
    checkout = tmp_path / "hermes"
    checkout.mkdir()
    _git(checkout, "init", "-q")
    _git(checkout, "config", "user.email", "test@example.invalid")
    _git(checkout, "config", "user.name", "Installer Test")
    (checkout / "agent.py").write_text(BASE_TEXT, encoding="utf-8")
    (checkout / "unrelated.txt").write_text("original\n", encoding="utf-8")
    _git(checkout, "add", "agent.py", "unrelated.txt")
    _git(checkout, "commit", "-qm", "base")
    head = _git(checkout, "rev-parse", "HEAD").stdout.strip()

    (checkout / "agent.py").write_text(PATCHED_TEXT, encoding="utf-8")
    patch_text = _git(checkout, "diff", "--binary", "--", "agent.py").stdout
    _git(checkout, "restore", "agent.py")

    project = tmp_path / "project"
    patch_dir = project / "patches" / "test"
    patch_dir.mkdir(parents=True)
    patch_path = patch_dir / "feature.patch"
    patch_path.write_text(patch_text, encoding="utf-8")
    digest = hashlib.sha256(patch_path.read_bytes()).hexdigest()
    manifest = project / "patches" / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "patches": [
                    {
                        "hermes_version": "test-version",
                        "upstream_commit": head,
                        "patch": "test/feature.patch",
                        "sha256": digest,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return checkout, manifest, patch_path


def _argv(checkout: Path, manifest: Path, command: str, *extra: str) -> list[str]:
    return [
        "--hermes-dir",
        str(checkout),
        "--manifest",
        str(manifest),
        command,
        *extra,
    ]


def test_install_is_idempotent_and_remove_is_reversible(synthetic_patch):
    checkout, manifest, _ = synthetic_patch

    assert inspect_patch(checkout, manifest=manifest).state == "available"
    assert main(_argv(checkout, manifest, "install")) == 0
    assert (checkout / "agent.py").read_text() == PATCHED_TEXT
    assert inspect_patch(checkout, manifest=manifest).state == "installed"

    assert main(_argv(checkout, manifest, "install")) == 0
    assert main(_argv(checkout, manifest, "remove", "--dry-run")) == 0
    assert (checkout / "agent.py").read_text() == PATCHED_TEXT
    assert main(_argv(checkout, manifest, "remove")) == 0
    assert (checkout / "agent.py").read_text() == BASE_TEXT
    assert inspect_patch(checkout, manifest=manifest).state == "available"


def test_install_rejects_sha_mismatch_without_mutation(synthetic_patch):
    checkout, manifest, patch = synthetic_patch
    patch.write_text(patch.read_text() + "\n", encoding="utf-8")

    assert main(_argv(checkout, manifest, "install")) == 2
    assert (checkout / "agent.py").read_text() == BASE_TEXT


def test_install_rejects_dirty_patch_touched_file(synthetic_patch):
    checkout, manifest, _ = synthetic_patch
    local_text = BASE_TEXT.replace("keep-10\n", "locally changed\n")
    (checkout / "agent.py").write_text(local_text, encoding="utf-8")

    status = inspect_patch(checkout, manifest=manifest)
    assert status.state == "available"
    assert status.overlapping_files == ("agent.py",)
    assert main(_argv(checkout, manifest, "install")) == 2
    assert (checkout / "agent.py").read_text() == local_text


def test_install_preserves_unrelated_dirty_file(synthetic_patch):
    checkout, manifest, _ = synthetic_patch
    (checkout / "unrelated.txt").write_text("user work\n", encoding="utf-8")

    assert main(_argv(checkout, manifest, "install")) == 0
    assert (checkout / "agent.py").read_text() == PATCHED_TEXT
    assert (checkout / "unrelated.txt").read_text() == "user work\n"


def _profile_fixture(tmp_path: Path):
    home = tmp_path / "hermes-home"
    profile = home / "profiles" / "sample"
    profile.mkdir(parents=True)
    auth = profile / "auth.json"
    auth.write_text(
        json.dumps(
            {
                "credential_pool": {
                    "anthropic": [
                        {
                            "id": "unrelated",
                            "label": "unrelated",
                            "source": "api_key",
                            "auth_type": "api_key",
                        }
                    ]
                },
                "preserved": True,
            }
        ),
        encoding="utf-8",
    )
    os.chmod(auth, 0o600)
    first = tmp_path / ".claude-one"
    second = tmp_path / ".claude-two"
    first.mkdir()
    second.mkdir()
    return home, auth, first, second


def test_configure_profile_backs_up_and_writes_metadata_only(tmp_path: Path):
    home, auth, first, second = _profile_fixture(tmp_path)
    result = main(
        [
            "--hermes-home",
            str(home),
            "configure-profile",
            "--profile",
            "sample",
            "--claude-dir",
            str(first),
            "--claude-dir",
            str(second),
            "--label",
            "first",
            "--label",
            "second",
            "--yes",
        ]
    )

    assert result == 0
    payload = json.loads(auth.read_text())
    assert payload["preserved"] is True
    assert len(payload["credential_pool"]["anthropic"]) == 3
    rows = configured_claude_rows(auth)
    assert [row["label"] for row in rows] == ["first", "second"]
    assert all("access_token" not in row for row in rows)
    assert all("refresh_token" not in row for row in rows)
    assert oct(auth.stat().st_mode & 0o777) == "0o600"
    backups = list((home / "backups" / "claude-patch-installer").rglob("auth.json"))
    assert len(backups) == 1
    original = json.loads(backups[0].read_text())
    assert original["credential_pool"]["anthropic"][0]["id"] == "unrelated"


def test_configure_profile_dry_run_changes_nothing(tmp_path: Path):
    home, auth, first, _ = _profile_fixture(tmp_path)
    original = auth.read_bytes()

    result = main(
        [
            "--hermes-home",
            str(home),
            "configure-profile",
            "--profile",
            "sample",
            "--claude-dir",
            str(first),
            "--dry-run",
        ]
    )

    assert result == 0
    assert auth.read_bytes() == original
    assert not (home / "backups").exists()


def test_configure_profile_rejects_path_traversal(tmp_path: Path):
    home, _, first, _ = _profile_fixture(tmp_path)

    result = main(
        [
            "--hermes-home",
            str(home),
            "configure-profile",
            "--profile",
            "../outside",
            "--claude-dir",
            str(first),
            "--yes",
        ]
    )

    assert result == 2
    assert not (home / "backups").exists()


@pytest.mark.parametrize("payload", [[], {"credential_pool": []}])
def test_profile_reader_rejects_malformed_roots(tmp_path: Path, payload):
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(InstallerError):
        configured_claude_rows(auth)


def test_setup_row_selection_is_explicit():
    rows = [
        {"label": "first", "priority": 0},
        {"label": "second", "priority": 1},
        {"label": "third", "priority": 2},
    ]

    args = type("Args", (), {"all": False, "slot": [2, 2, 1]})()
    assert [row["label"] for row in _select_setup_rows(rows, args)] == [
        "second",
        "first",
    ]


def test_manifest_matches_versioned_patch():
    manifest = json.loads((Path("patches") / "manifest.json").read_text())
    entry = manifest["patches"][0]
    patch = Path("patches") / entry["patch"]
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == entry["sha256"]
