#!/usr/bin/env python3
"""Package the available Unity players and prepare the Pages WebGL copy."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

CHUNK_SIZE = 90 * 1024 * 1024  # Leave comfortable room below GitHub's 100 MiB object limit.
NAMES = {
    "windows": "angry-birds-epic-windows-x64.zip",
    "macos": "angry-birds-epic-macos.zip",
    "android": "angry-birds-epic-android.apk",
    "ios": "angry-birds-epic-ios-xcode-project.zip",
    "webgl": "angry-birds-epic-webgl.zip",
}


def archive_with_ditto(source: Path, destination: Path) -> None:
    subprocess.run(
        ["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(source), str(destination)],
        check=True,
    )


def split_webgl_data(webgl_copy: Path) -> None:
    data_file = webgl_copy / "Build" / "Epic.data"
    if not data_file.is_file():
        raise FileNotFoundError(f"Expected WebGL data file: {data_file}")

    original_size = data_file.stat().st_size
    expected_parts = (original_size + CHUNK_SIZE - 1) // CHUNK_SIZE
    index = 1
    with data_file.open("rb") as source:
        while chunk := source.read(CHUNK_SIZE):
            part = data_file.with_name(f"Epic.data.part-{index:03d}")
            part.write_bytes(chunk)
            index += 1
    if index - 1 != expected_parts:
        raise RuntimeError("WebGL data file could not be split into complete parts.")
    data_file.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("players_dir", type=Path, help="Unity BuildArtifacts/Players directory")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1], help="Repository root")
    args = parser.parse_args()

    players = args.players_dir.expanduser().resolve()
    repo = args.repo.expanduser().resolve()
    output = repo / "_release-assets"
    webgl_copy = repo / "play"

    if shutil.which("ditto") is None:
        raise SystemExit("This packaging script requires macOS ditto to preserve .app bundles and project metadata.")

    sources = {
        "windows": players / "StandaloneWindows64",
        "macos": players / "StandaloneOSX" / "Epic.app",
        "android": players / "Android" / "Epic.apk",
        "ios": players / "iOS" / "Epic",
        "webgl": players / "WebGL" / "Epic",
    }
    for key, source in sources.items():
        if not source.exists():
            raise FileNotFoundError(f"Missing {key} build: {source}")

    if output.exists():
        shutil.rmtree(output)
    if webgl_copy.exists():
        shutil.rmtree(webgl_copy)
    output.mkdir(parents=True)

    archive_with_ditto(sources["windows"], output / NAMES["windows"])
    archive_with_ditto(sources["macos"], output / NAMES["macos"])
    shutil.copy2(sources["android"], output / NAMES["android"])
    archive_with_ditto(sources["ios"], output / NAMES["ios"])
    archive_with_ditto(sources["webgl"], output / NAMES["webgl"])

    shutil.copytree(sources["webgl"], webgl_copy, symlinks=True)
    (webgl_copy / "index.html").write_text((repo / "site" / "player-index.html").read_text())
    shutil.copy2(repo / "site" / "player.css", webgl_copy / "player.css")
    shutil.copy2(repo / "site" / "player.js", webgl_copy / "player.js")
    shutil.copy2(repo / "site" / "player-sw.js", webgl_copy / "sw.js")
    split_webgl_data(webgl_copy)

    manifest = {
        key: {"file": filename, "size": (output / filename).stat().st_size}
        for key, filename in NAMES.items()
    }
    (repo / "builds.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared release files in {output}")
    print(f"Prepared full-screen Pages WebGL player in {webgl_copy}")
    for key, item in manifest.items():
        print(f"{key}: {item['size']:,} bytes ({item['file']})")


if __name__ == "__main__":
    main()
