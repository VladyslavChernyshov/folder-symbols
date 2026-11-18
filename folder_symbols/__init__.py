"""Folder Symbols: put a symbolic icon on Yaru's folder icon, in Yaru's own embossed style.

Modules:
  engine   theme-independent rendering and compositing (symbol masks, emboss, rasterising)
  yaru     everything specific to Yaru: sizes, geometry, calibration, templates, assets/themes.json
  symbols  finding *-symbolic.svg files and the per-symbol overrides.json
  svg      the scalable (SVG) output
  batch    many symbols x themes x sizes in parallel
  apply    setting / removing folders' custom icons with gio and recording them (the library the window uses)
  commands the CLI's manifest commands: apply, reset, list, prune (print and exit)
  store    the local store: manifest.json (one recipe per folder) and the generated icons
  cli      argument parsers and main()
  accents  the accent picker's data and its follow-the-system state (no GTK)
  appinfo  the welcome page texts, the About dialog data, which page the window shows, and warn() for the window's stderr lines (no GTK)
  gallery  the symbol gallery's data: listing, categories, filtering, and loading the symbols with the "Symbols not found" page texts (no GTK)
  initial  the window's initial state for a folder selection, from the manifest only (no GTK)
  outcome  what the window does after Apply, Reset or Clean up (no GTK)
  preview  the GUI's folder preview, built as an SVG in a temporary directory (no GTK)
  selection  launch path normalisation and the sidebar header text (no GTK)
  gui      the GTK4/libadwaita window; the only subpackage that imports GTK
"""
__version__ = "0.2.0"   # the one place the version lives; tag releases as v<__version__>
