# Legacy Windows CLI

This folder archives the earlier portable Windows version of FH Road Finder.
The browser tool on the repository front page is the recommended version for
most users. This CLI is kept for anyone who prefers local batch processing.

## Included Files

```text
legacy-windows-cli/
|-- Run_FH6_Road_Finder.bat
|-- README.md
|-- archive-notes/
|   `-- ROAD_FINDER_REVIEW_NOTES.txt
`-- tools/
    `-- fh6_road_finder.py
```

The launcher creates these local working folders automatically when you run it:

```text
input/
output/
.venv/
```

## Requirements

- Windows
- Python 3
- An internet connection the first time you run the launcher

The BAT launcher creates a local `.venv` and installs its dependencies there:

- `pillow`
- `numpy`
- `opencv-python`

It does not require administrator rights.

## How To Run

1. Download or clone this repository.
2. Open the `legacy-windows-cli` folder.
3. Put your map screenshots inside its `input` folder. The BAT file creates the
   folder automatically the first time it runs.
4. Double-click `Run_FH6_Road_Finder.bat`.
5. Pick a tolerance option.
6. Open `output\report.html`.
7. Check the generated `*_overlay.png` images first.

For clean PNG screenshots, start with option `6`, which runs tolerance values
`0`, `1`, and `2`. For JPEG screenshots, try option `4`, which uses tolerance
`5` to compensate for compression colour shifts.

## What It Generates

For each screenshot and tolerance value, the CLI can create:

- Overlay PNGs with highlighted pixels on the original screenshot
- Black-background highlight PNGs
- Transparent highlight-mask PNGs
- `output\report.html`

The detector targets `RGB(128,128,128)`, based on `HSV(0,0,50.2)`. It uses
per-channel matching by default:

```text
abs(R - target_R) <= tolerance
abs(G - target_G) <= tolerance
abs(B - target_B) <= tolerance
```

The launcher uses a minimum cluster size of `8` pixels. The Python script also
supports manual CLI options if you want to adjust advanced settings directly.

## Historical Notes

The `archive-notes` folder preserves the earlier road-finder review handoffs.
They are included for reference only and are not required to run the CLI.

## Notes

- PNG is recommended because JPEG compression changes pixel colours.
- Original screenshots are never modified.
- CSV files are intentionally not generated in this archived version.
- Generated screenshots, reports, and the local `.venv` are not included in
  this repository archive.
