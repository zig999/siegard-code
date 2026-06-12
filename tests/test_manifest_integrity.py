"""Manifest integrity — siegard-manifest.json is present, valid, and FRESH.

The freshness tests recompute every hash over dist/.claude/ using the same
walk/hash rules as generation (imported from verify_install.py). A stale
manifest — any dist file added, removed, or edited after the last
`python3 gen_manifest.py` run — fails the suite, which is what makes the
committed manifest trustworthy without install-time tooling.
"""
import json
import re
import sys
from datetime import datetime

from conftest import DIST_DIR

sys.path.insert(0, str(DIST_DIR / "scripts"))

from verify_install import MANIFEST_NAME, hash_file, iter_managed_files

MANIFEST_PATH = DIST_DIR / MANIFEST_NAME
REQUIRED_FIELDS = ["framework", "version", "source", "generated_at",
                   "hash_normalization", "files"]
_SEMVER = re.compile(r"\d+\.\d+\.\d+")


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


class TestManifestSchema:
    def test_manifest_exists(self):
        assert MANIFEST_PATH.is_file(), \
            f"{MANIFEST_NAME} missing — run: python3 gen_manifest.py --version X.Y.Z"

    def test_required_fields(self):
        manifest = _manifest()
        for field in REQUIRED_FIELDS:
            assert field in manifest, f'"{field}" missing in {MANIFEST_NAME}'

    def test_version_is_semver(self):
        assert _SEMVER.fullmatch(_manifest()["version"]), \
            "version must be X.Y.Z"

    def test_source_repository_present(self):
        assert _manifest()["source"].get("repository"), \
            "source.repository must be a non-empty URL"

    def test_generated_at_is_iso8601_utc(self):
        generated_at = _manifest()["generated_at"]
        assert generated_at.endswith("Z"), "generated_at must be UTC (Z suffix)"
        datetime.fromisoformat(generated_at.replace("Z", "+00:00"))

    def test_hash_normalization_declared(self):
        assert _manifest()["hash_normalization"] == "text-lf"

    def test_files_nonempty_sorted_unique(self):
        paths = [f["path"] for f in _manifest()["files"]]
        assert paths, "files inventory is empty"
        assert paths == sorted(paths), "files must be sorted by path"
        assert len(paths) == len(set(paths)), "duplicate paths in files"

    def test_entries_have_path_and_sha256(self):
        for entry in _manifest()["files"]:
            assert set(entry) == {"path", "sha256"}, f"bad entry shape: {entry}"
            assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]), \
                f'invalid sha256 for {entry["path"]}'


class TestManifestFreshness:
    def test_inventory_matches_dist(self):
        manifest_paths = {f["path"] for f in _manifest()["files"]}
        dist_paths = set(iter_managed_files(DIST_DIR))
        only_manifest = manifest_paths - dist_paths
        only_dist = dist_paths - manifest_paths
        assert not only_manifest and not only_dist, (
            f"manifest is stale — run gen_manifest.py. "
            f"In manifest but not in dist: {sorted(only_manifest)}; "
            f"in dist but not in manifest: {sorted(only_dist)}"
        )

    def test_hashes_match_dist(self):
        stale = [
            entry["path"] for entry in _manifest()["files"]
            if (DIST_DIR / entry["path"]).is_file()
            and hash_file(DIST_DIR / entry["path"]) != entry["sha256"]
        ]
        assert not stale, \
            f"manifest is stale — run gen_manifest.py. Hash drift: {stale}"

    def test_exclusions_respected(self):
        for path in (f["path"] for f in _manifest()["files"]):
            assert "__pycache__" not in path, f"__pycache__ leaked: {path}"
            assert not path.endswith(".pyc"), f".pyc leaked: {path}"
            assert path != MANIFEST_NAME, "manifest must not list itself"
