# GUI resources

Maintainer reference for the icons and logos shipped with the desktop viewer.

## Layout

```text
resources/
├── icons/svg/       source toolbar icons
├── icons/png/24/    raster fallback
├── icons/png/48/    HiDPI raster fallback
├── logo/            viewer, report and Windows assets
├── gen/             asset definitions and generator
└── resources.qrc    Qt resource manifest
```

## Runtime behavior

`compare_tool/resources.py` resolves assets in both a source checkout and a frozen executable. `compare_tool/qtviewer/icons.py` loads and tints them for the active theme.

Missing assets must degrade to text labels or an empty icon; they must not prevent comparison or viewer startup.

## Editing rules

- Keep SVG icons on a 24×24 grid with `stroke="currentColor"`.
- Put application colors in `compare_tool/theme.py`; do not add viewer color literals here.
- Keep PNG and ICO fallbacks in sync with their SVG sources.
- Add new packaged assets to `resources.qrc` and the PyInstaller spec when required.
- Generated assets are committed so runtime use never needs CairoSVG, Pillow or network access.

Verify resource lookup with:

```bash
python -m unittest tests.test_resources -v
```
