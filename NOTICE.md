# Attribution

The folder drawings, folder icons and symbolic icons that this project's templates and generated
files are built from are part of the **Yaru** theme (https://github.com/ubuntu/yaru), by the Yaru
project contributors and Canonical Ltd. Per Yaru's `debian/copyright`, the icon artwork
(`icons/*`, Sam Hewitt and contributors) is licensed under **Creative Commons
Attribution-ShareAlike 4.0** (https://creativecommons.org/licenses/by-sa/4.0/).

## What is derived from Yaru

* `assets/folder-template.svg` and `assets/folder-template-mate.svg` are excerpts of Yaru's
  `src/fullcolor/accented-full/places/folders.svg` and of its MATE counterpart: the drawing of
  one folder (the `folder (clone source)` group), with its gradients, clip paths and filters,
  stripped of editor metadata, plus two marker comments where the script inserts a symbol. The
  placeholder colours of Yaru's template are kept. Changes: cut out, cleaned, markers added.
  They are distributed under **CC BY-SA 4.0**.
* `assets/themes.json` holds numbers measured from Yaru's icon PNGs (colours and the position of
  the folder's front panel for each variant). It contains no artwork; it is distributed under
  CC BY-SA 4.0 together with the templates it belongs to.
* The generated icons (SVG and PNG, including those in this project's releases) are adaptations
  of that artwork: a symbol composited onto a folder, with Yaru's emboss effect reproduced.
  They are distributed under the same licence, **CC BY-SA 4.0**. The symbol's own licence also
  applies to the symbol part (see below).

Changes: symbol and folder combined; no endorsement by Yaru, Canonical or the original authors is
implied.

Individual symbolic icons may carry other licences upstream; check Yaru's `debian/copyright` for
details before redistributing a specific icon.

* `tools/screenshot_parts/*.png` are cut from screenshots of the GNOME Files (Nautilus) window drawn
  with the Yaru GTK theme (window frame, buttons, folder names) and are used only to draw the fake
  screenshot in the README. They are distributed under **CC BY-SA 4.0** like the rest of Yaru's
  artwork; Nautilus itself is GPL-3.0-or-later software by the GNOME project.

## What is original

The script `yaru-folder-icon.py`, the tools in `tools/`, the tests and the workflow files are
original code under the **MIT** licence (see `LICENSE`). The script does not contain Yaru code; it
reads icons installed on the user's system (or from Yaru's source tree), the two templates and
`themes.json` in `assets/`.

`tools/extract_template.py` only reads a Yaru source sheet that the user supplies and writes a
template from it; it does not include any Yaru artwork itself.
