# Angry Birds Epic Builds

A small community archive site for the available Angry Birds Epic builds. The page is a static site and uses relative URLs, so it works as a GitHub Pages project site at `/<repository-name>/`.

## Local preview

On macOS, run:

```sh
./scripts/preview.sh
```

Then open the URL printed by the script. It serves the project under `/abebuilds/`, matching the GitHub Pages project-site path. The platform packages are available locally in `_release-assets/`.

The WebGL player opens in a new page and fills the viewport. Tap **Enter game** to request browser full screen and landscape orientation where supported. Mobile browsers control their own navigation bars; for the most app-like iPhone view, add the game page to the Home Screen and launch it from there.

## Build packages

The complete Windows folder, macOS `Epic.app`, iOS Xcode project, and original WebGL folder are stored as ZIP files in the ignored `_release-assets/` directory. The Android APK is copied there directly. These files are prepared for a GitHub Release and are intentionally not part of Git history. Each release asset must stay below GitHub's per-file upload limit.

The Pages copy in `play/` contains the complete Unity runtime files, including every file from `Build` and `StreamingAssets`. The original `Epic.data` is larger than GitHub's 100 MiB per-file limit, so the Pages copy stores that file as consecutive 90 MiB chunks. `sw.js` streams those chunks back as the original `Build/Epic.data` response when Unity requests it. The chunks preserve the exact original bytes; the Unity source build is not edited. The ZIP in `_release-assets/` keeps the original build layout.

To recreate packages and the Pages copy on the original build Mac:

```sh
python3 scripts/prepare-builds.py \
  "/Users/yaroslavsazhchenko/Documents/programming/unity/ABE/BuildArtifacts/Players"
```

The script requires macOS `ditto` so application bundles, file permissions, and project structure are preserved.

## GitHub Pages setup

1. Push the site files to the `main` branch.
2. In the repository's **Settings → Pages**, choose **Deploy from a branch**, select `main`, and choose `/(root)`.
3. Attach the files from `_release-assets/` to a GitHub Release. The site buttons point to the latest release assets; they become downloadable after those assets are published.

The Pages output is under 1 GB. Keep the game and download archives out of normal Git history: GitHub rejects individual Git files over 100 MiB, and recommends Releases for large binaries. Git LFS is not supported by GitHub Pages.

No GitHub Release has been created, and no GitHub Pages settings have been changed.

## Notes

- The iOS download is an Xcode project, not a signed IPA. Xcode and code signing are required to install it.
- Linux is marked unavailable because the latest Linux IL2CPP build did not finish; the macOS build host lacks the Linux IL2CPP system headers.
- This is an unofficial fan-made community project. Angry Birds Epic, its names, characters, and game assets belong to their respective rights holders.
