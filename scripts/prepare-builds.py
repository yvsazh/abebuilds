#!/usr/bin/env python3
"""Package the available Unity players and prepare the Pages WebGL copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

CHUNK_SIZE = 90 * 1024 * 1024  # Leave comfortable room below GitHub's 100 MiB object limit.
NAMES = {
    "windows": "angry-birds-epic-windows-x64.zip",
    "macos": "angry-birds-epic-macos.zip",
    "android": "angry-birds-epic-android.apk",
    "ios": "angry-birds-epic-ios-xcode-project.zip",
    "webgl": "angry-birds-epic-webgl.zip",
}
TARGETS = {
    "windows": "StandaloneWindows64",
    "macos": "StandaloneOSX",
    "android": "Android",
    "ios": "iOS",
    "webgl": "WebGL",
}


def validate_release_builds(players: Path) -> None:
    report = players.parent / "Validation" / "build-matrix.txt"
    if not report.is_file():
        raise SystemExit(f"Build report is missing: {report}")

    lines = report.read_text(errors="replace").splitlines()
    if not any(line.startswith("Unity ") and "; UTC " in line for line in lines):
        raise SystemExit(f"Build report has no build history: {report}")

    for platform, target in TARGETS.items():
        rows = [line for line in lines if line.startswith(target + " ")]
        if not rows:
            raise SystemExit(f"Build report has no result for {platform} ({target}). Build the release target first.")
        result = rows[-1]
        if not all(
            marker in result
            for marker in (" SUCCEEDED ", "report=Succeeded", "editorDevelopment=False", "options=None", "development=False")
        ):
            raise SystemExit(f"Refusing to package {platform}: its latest result is not a verified release build.\n{result}")


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


def webgl_build_version(webgl_source: Path, site_source: Path) -> str:
    digest = hashlib.sha256()
    inputs = [
        (webgl_source, "Build/Epic.loader.js"),
        (webgl_source, "Build/Epic.framework.js"),
        (webgl_source, "Build/Epic.wasm"),
        (webgl_source, "Build/Epic.data"),
        (site_source, "player-index.html"),
        (site_source, "player.js"),
        (site_source, "player.css"),
        (site_source, "player-sw.js"),
    ]
    for base, relative_path in inputs:
        source = base / relative_path
        if not source.is_file():
            raise FileNotFoundError(f"Expected WebGL build file: {source}")
        with source.open("rb") as stream:
            while chunk := stream.read(8 * 1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()[:16]


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
    validate_release_builds(players)

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
    webgl_version = webgl_build_version(sources["webgl"], repo / "site")

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
    player_html = (repo / "site" / "player-index.html").read_text().replace("__WEBGL_BUILD_VERSION__", webgl_version)
    player_worker = (repo / "site" / "player-sw.js").read_text().replace("__WEBGL_BUILD_VERSION__", webgl_version)
    if "__WEBGL_BUILD_VERSION__" in player_html or "__WEBGL_BUILD_VERSION__" in player_worker:
        raise RuntimeError("WebGL build version was not inserted into the player files.")
    (webgl_copy / "index.html").write_text(player_html)
    shutil.copy2(repo / "site" / "player.css", webgl_copy / "player.css")
    shutil.copy2(repo / "site" / "player.js", webgl_copy / "player.js")
    (webgl_copy / "sw.js").write_text(player_worker)
    split_webgl_data(webgl_copy)

    # Test status is maintained by hand in site/platform-status.json; only claim what was verified.
    status = json.loads((repo / "site" / "platform-status.json").read_text())
    missing = [key for key in NAMES if key not in status]
    if missing:
        raise SystemExit(f"site/platform-status.json has no entry for: {', '.join(missing)}")
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    manifest = {
        key: {
            "file": filename,
            "size": (output / filename).stat().st_size,
            "built": generated,
            **status[key],
        }
        for key, filename in NAMES.items()
    }
    (repo / "builds.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared release files in {output}")
    print(f"Prepared full-screen Pages WebGL player in {webgl_copy}")
    for key, item in manifest.items():
        print(f"{key}: {item['size']:,} bytes ({item['file']})")


if __name__ == "__main__":
    main()
