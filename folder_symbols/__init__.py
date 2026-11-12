"""Folder Symbols: put a symbolic icon on Yaru's folder icon, in Yaru's own embossed style.

Modules:
  engine   theme-independent rendering and compositing (symbol masks, emboss, rasterising)
  yaru     everything specific to Yaru: sizes, geometry, calibration, templates, assets/themes.json
  symbols  finding *-symbolic.svg files and the per-symbol overrides.json
  svg      the scalable (SVG) output
  batch    many symbols x themes x sizes in parallel
  apply    setting / removing a folder's custom icon with gio, list, reset --all, prune
  store    the local store: manifest.json (one recipe per folder) and the generated icons
  cli      argument parsers and main()
"""
__version__ = "0.1.0"   # the one place the version lives; tag releases as v<__version__>
