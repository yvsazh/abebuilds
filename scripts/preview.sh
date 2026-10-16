#!/bin/sh
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PREVIEW_DIR=$(mktemp -d "${TMPDIR:-/tmp}/abebuilds-preview.XXXXXX")
cleanup() {
  rm -rf "$PREVIEW_DIR"
}
trap cleanup EXIT INT TERM

ln -s "$REPO_DIR" "$PREVIEW_DIR/abebuilds"
printf 'Preview: http://127.0.0.1:4173/abebuilds/\nPress Ctrl-C to stop.\n'
cd "$PREVIEW_DIR"
python3 -m http.server 4173 --bind 127.0.0.1
