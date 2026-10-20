#!/usr/bin/env python3
"""Reject prohibited assistant attribution in repository content and Git metadata."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import BinaryIO


_TOKENS = ("cl" + "aude", "anthr" + "opic")
_SEPARATOR = rb"[\s._-]{0,3}"
_PATTERNS = tuple(
    re.compile(
        rb"(?i)" + _SEPARATOR.join(re.escape(bytes((letter,))) for letter in token.encode("ascii"))
    )
    for token in _TOKENS
)
_ZERO_OID = re.compile(r"^0+$")
_ERRORS: list[str] = []


def git(args: list[str], *, input_data: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", *args],
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(detail or f"git {' '.join(args)} failed")
    return result.stdout


def contains_prohibited(data: bytes) -> bool:
    return any(pattern.search(data) for pattern in _PATTERNS)


def report_if_found(data: bytes, location: str) -> bool:
    if not contains_prohibited(data):
        return False
    _ERRORS.append(location)
    return True


def scan_stream(stream: BinaryIO, location: str, first: bytes | None = None) -> bool:
    sample = stream.read(8192) if first is None else first
    overlap = b""
    chunk = sample
    matched = False
    while chunk:
        window = overlap + chunk
        if any(pattern.search(window) for pattern in _PATTERNS):
            _ERRORS.append(location)
            matched = True
            break
        overlap = window[-64:]
        chunk = stream.read(1024 * 1024)
    return matched


def scan_blob(oid: str, location: str) -> bool:
    process = subprocess.Popen(
        ["git", "cat-file", "blob", oid],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    first = process.stdout.read(8192)
    matched = scan_stream(process.stdout, location, first)
    if matched:
        process.stdout.close()
    return_code = process.wait()
    if return_code and not matched:
        assert process.stderr is not None
        detail = process.stderr.read().decode("utf-8", "replace").strip()
        raise RuntimeError(detail or f"could not read blob {oid}")
    return matched


def scan_worktree_file(root: Path, path_bytes: bytes) -> None:
    path = root / os.fsdecode(path_bytes)
    try:
        if path.is_symlink():
            report_if_found(os.fsencode(os.readlink(path)), f"file {os.fsdecode(path_bytes)}")
            return
        if not path.is_file():
            return
        with path.open("rb") as stream:
            scan_stream(stream, f"file {os.fsdecode(path_bytes)}")
    except OSError as exc:
        raise RuntimeError(f"could not inspect {os.fsdecode(path_bytes)}: {exc}") from exc


def inspect_all_worktree_files() -> None:
    root = Path(os.fsdecode(git(["rev-parse", "--show-toplevel"]).strip()))
    paths = git(["ls-files", "-z"]).split(b"\x00")
    for path in paths:
        if path:
            scan_worktree_file(root, path)


def inspect_staged_files() -> None:
    changed = set(
        path
        for path in git(
            ["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
        ).split(b"\x00")
        if path
    )
    if not changed:
        return

    staged: dict[bytes, tuple[str, str, str]] = {}
    for record in git(["ls-files", "--stage", "-z"]).split(b"\x00"):
        if not record:
            continue
        metadata, path = record.split(b"\t", 1)
        mode, oid, stage = metadata.decode("ascii").split()
        staged[path] = (mode, oid, stage)

    for path in changed:
        entry = staged.get(path)
        if entry is None:
            continue
        mode, oid, stage = entry
        if stage != "0":
            raise RuntimeError("resolve staged merge conflicts before committing")
        if mode == "160000":
            continue
        scan_blob(oid, f"staged file {os.fsdecode(path)}")


def commit_data(oid: str) -> tuple[bytes, list[str]]:
    raw = git(["cat-file", "commit", oid])
    header = raw.partition(b"\n\n")[0]
    parents = [
        line[7:].decode("ascii")
        for line in header.splitlines()
        if line.startswith(b"parent ")
    ]
    return raw, parents


def tree_entries(oid: str) -> dict[bytes, tuple[bytes, str]]:
    entries: dict[bytes, tuple[bytes, str]] = {}
    listing = git(["ls-tree", "-r", "-z", "--full-tree", oid])
    for record in listing.split(b"\x00"):
        if not record:
            continue
        metadata, path = record.split(b"\t", 1)
        mode, object_type, object_oid = metadata.split()
        entries[path] = (mode, object_oid.decode("ascii"))
    return entries


def changed_paths(commit: str, parents: list[str]) -> set[bytes]:
    if not parents:
        return set(tree_entries(commit))
    listing = git(
        [
            "diff",
            "--no-ext-diff",
            "--no-renames",
            "--name-only",
            "--diff-filter=ACMR",
            "-z",
            parents[0],
            commit,
            "--",
        ]
    )
    return {path for path in listing.split(b"\x00") if path}


def inspect_history(ref: str, scanned_blobs: set[str]) -> None:
    commits = git(["rev-list", "--reverse", ref]).decode("ascii").splitlines()
    for oid in commits:
        raw, parents = commit_data(oid)
        report_if_found(raw, f"commit {oid}")
        entries = tree_entries(oid)
        for path in changed_paths(oid, parents):
            entry = entries.get(path)
            if entry is None:
                continue
            mode, blob_oid = entry
            if mode == b"160000" or blob_oid in scanned_blobs:
                continue
            scanned_blobs.add(blob_oid)
            scan_blob(blob_oid, f"file history at {oid}:{os.fsdecode(path)}")


def inspect_tag_object(oid: str) -> str:
    current = oid
    while git(["cat-file", "-t", current]).strip() == b"tag":
        raw = git(["cat-file", "tag", current])
        report_if_found(raw, f"tag object {current}")
        object_line = next(
            (line for line in raw.splitlines() if line.startswith(b"object ")), None
        )
        if object_line is None:
            raise RuntimeError(f"tag object {current} has no target")
        current = object_line[7:].decode("ascii")
    return current


def inspect_tree(oid: str, scanned_blobs: set[str]) -> None:
    for path, (mode, blob_oid) in tree_entries(oid).items():
        if mode == b"160000" or blob_oid in scanned_blobs:
            continue
        scanned_blobs.add(blob_oid)
        scan_blob(blob_oid, f"tree content {oid}:{os.fsdecode(path)}")


def inspect_object(oid: str, scanned_blobs: set[str]) -> None:
    object_type = git(["cat-file", "-t", oid]).strip()
    if object_type == b"tag":
        oid = inspect_tag_object(oid)
        object_type = git(["cat-file", "-t", oid]).strip()
    if object_type == b"commit":
        inspect_history(oid, scanned_blobs)
    elif object_type == b"tree":
        inspect_tree(oid, scanned_blobs)
    elif object_type == b"blob" and oid not in scanned_blobs:
        scanned_blobs.add(oid)
        scan_blob(oid, f"ref content {oid}")


def inspect_all_refs() -> None:
    scanned_blobs: set[str] = set()
    refs = git(
        ["for-each-ref", "--format=%(refname) %(objectname) %(objecttype)"]
    ).decode("utf-8", "replace").splitlines()
    for line in refs:
        _ref, oid, _object_type = line.split(" ", 2)
        inspect_object(oid, scanned_blobs)
    head = git(["rev-parse", "--verify", "HEAD"]).decode().strip()
    inspect_object(head, scanned_blobs)


def inspect_identity() -> None:
    for variable in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
        identity = git(["var", variable])
        report_if_found(identity, f"{variable.lower().replace('_', ' ')}")


def inspect_message_file(path: str) -> None:
    with open(path, "rb") as message:
        report_if_found(message.read(), "commit message")


def inspect_push_input() -> None:
    updates = sys.stdin.buffer.read().splitlines()
    refs_to_check: set[str] = set()
    for update in updates:
        fields = update.split()
        if len(fields) != 4:
            raise RuntimeError("could not parse Git pre-push input")
        local_ref, local_oid, _remote_ref, _remote_oid = fields
        local_hash = local_oid.decode("ascii")
        if _ZERO_OID.fullmatch(local_hash):
            continue
        refs_to_check.add(local_oid.decode("ascii"))

    scanned_blobs: set[str] = set()
    for oid in refs_to_check:
        inspect_object(oid, scanned_blobs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-files", action="store_true")
    parser.add_argument("--all-refs", action="store_true")
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--identity", action="store_true")
    parser.add_argument("--message-file")
    parser.add_argument("--push-input", action="store_true")
    args = parser.parse_args()

    try:
        if args.all_files:
            inspect_all_worktree_files()
        if args.all_refs:
            inspect_all_refs()
        if args.staged:
            inspect_staged_files()
        if args.identity:
            inspect_identity()
        if args.message_file:
            inspect_message_file(args.message_file)
        if args.push_input:
            inspect_push_input()
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Attribution guard could not complete: {exc}", file=sys.stderr)
        return 2

    if _ERRORS:
        for location in sorted(set(_ERRORS)):
            print(f"Blocked prohibited attribution in {location}.", file=sys.stderr)
        return 1

    print("Attribution checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
