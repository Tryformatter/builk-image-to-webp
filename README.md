# WebP Forge

A private Windows desktop utility for converting many images to WebP at once. Images are processed locally and never uploaded.

Prefer the browser? Use the branded
[TryFormatter Image to WebP converter](https://www.tryformatter.com/image/image-to-webp)
with no software installation and no file upload. Processing stays in your browser.

## Features

- Add individual images or scan entire folders
- Drag and drop images or folders into the app
- JPG, JPEG, PNG, BMP, TIFF, and GIF input
- Lossy quality control or lossless WebP
- Preserves transparency and optional metadata/color profiles
- Choose an output folder or save beside originals
- Collision-safe output naming and optional overwrite
- Responsive progress display with cancellation

## Run from source

```powershell
python -m pip install -r requirements.txt
python app.py
```

## Build the Windows executable

```powershell
.\build.ps1
```

The standalone executable is created at `dist\WebP-Forge.exe`.

## Download a GitHub Actions build

Every push to `main` creates a tested Windows executable. Open the repository's
**Actions** tab, select the latest **Build Windows executable** run, and download
the `WebP-Forge-windows-x64` artifact.

Successful pushes to `main` also publish `WebP-Forge.exe` automatically on the
[GitHub Releases page](https://github.com/Tryformatter/builk-image-to-webp/releases).

Note: animated GIFs are converted using their first frame.
