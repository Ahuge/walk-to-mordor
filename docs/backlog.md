# Backlog

Future work, not yet scheduled.

## Tiled 20k Map

**Problem:** At 5k (5000×4344), the map isn't high enough quality when super-zoomed in the widget.

**Solution:** Generate a tiled slippy map from the 20k source image.

**Work required:**
- Tile generation pipeline (`gdal2tiles.py` or similar) — one-time build step, or CI
- Storage: 100s of MB of 256×256 tiles across zoom levels
- Bundle strategy: ship tiles with PyInstaller? Or host separately?
- Leaflet: switch from `imageOverlay` to `tileLayer`
- Coordinate mapping: journey path (currently in image pixels) needs conversion to tile coords

**Decision needed:** Bundle tiles in the installer (bigger download) vs. fetch from a server (needs hosting).

**Priority:** Medium. The 5k map works; this is a quality upgrade for zoom.
