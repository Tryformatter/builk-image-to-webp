# WebP Forge

A private Windows desktop utility for converting many images to WebP at once. Images are processed locally and never uploaded.

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

Note: animated GIFs are converted using their first frame.
