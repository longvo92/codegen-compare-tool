# GUI resources

Icons and logos bundled with the desktop viewer.

| Path | Content |
|---|---|
| `icons/svg/` | Source toolbar icons |
| `icons/png/24/`, `icons/png/48/` | Raster fallbacks |
| `logo/` | Viewer, report and Windows assets |
| `gen/` | Asset definitions and generator |
| `resources.qrc` | Qt resource manifest |

`compare_tool/resources.py` resolves source/frozen assets; `compare_tool/qtviewer/icons.py` loads and tints them. Missing assets fall back to text or empty icons without preventing startup or comparison.

## Editing

- Use a 24×24 SVG grid with `stroke="currentColor"`; define app colors in `compare_tool/theme.py`.
- Keep PNG/ICO fallbacks synchronized with SVG sources.
- Update `resources.qrc` and the PyInstaller spec when adding packaged assets.
- Commit generated assets so runtime needs no generator dependencies or network.

Verify lookup with `python -m unittest tests.test_resources -v`.
