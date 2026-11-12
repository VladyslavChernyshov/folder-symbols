#!/usr/bin/env python3
"""Build release archives for the yaru-folder-icons icon repository.

For every Yaru variant it writes one zip with all symbols as scalable SVG
(and, with --png, one zip with 512 px PNGs), plus SHA256SUMS.txt and
RELEASE_NOTES.md. Upload the contents of --out as release assets.

Examples:
  tools/make_release.py --out ~/release --symbols-dir /usr/share/icons/Yaru/scalable
  tools/make_release.py --out ~/release --png --icons-root ~/yaru-src/src/icons
"""
import argparse, hashlib, subprocess, sys, tempfile, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "folder-symbols"

README = """Yaru folder icons with symbols
==============================
Generated with Folder Symbols: https://github.com/VladyslavChernyshov/folder-symbols
Theme variant: {theme}   Format: {fmt}

Apply to a folder (GNOME / Nautilus):
  gio set /path/to/folder metadata::custom-icon file:///path/to/icon.{ext}

Licence: derivative of Yaru's folder icon (CC BY-SA 4.0,
https://github.com/ubuntu/yaru). These icons are shared under the same licence.
"""


def run(cmd):
    print("+", " ".join(map(str, cmd)), flush=True)
    subprocess.run(cmd, check=True)


def zip_theme(stage, theme, sub, out, fmt, ext):
    src = stage / theme / sub
    name = f"yaru-folder-icons-{theme}-{fmt}.zip"
    with zipfile.ZipFile(out / name, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr(f"{theme}/README.txt", README.format(theme=theme, fmt=fmt, ext=ext))
        for f in sorted(src.glob(f"*.{ext}")):
            z.write(f, f"{theme}/{f.name}")
    return out / name


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path, help="directory for the archives")
    ap.add_argument("--symbols-dir", help="directory with *-symbolic.svg (default: Yaru's)")
    ap.add_argument("--icons-root", help="directory with Yaru* theme dirs (needed for --png)")
    ap.add_argument("--themes", default="all", help="'all' or comma-separated list")
    ap.add_argument("--png", action="store_true", help="also build 512 px PNG archives")
    ap.add_argument("--only", help="regex: only matching symbols (for trial runs)")
    ap.add_argument("--tag", default="v1", help="release tag used in RELEASE_NOTES.md")
    a = ap.parse_args()

    a.out.mkdir(parents=True, exist_ok=True)
    sizes = "svg,512" if a.png else "svg"
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        cmd = [sys.executable, SCRIPT, "batch", "--out", stage, "--themes", a.themes, "--sizes", sizes]
        for flag, val in (("--symbols-dir", a.symbols_dir), ("--icons-root", a.icons_root), ("--only", a.only)):
            if val:
                cmd += [flag, val]
        run(cmd)
        zips = []
        for tdir in sorted(p for p in stage.iterdir() if p.is_dir()):
            zips.append(zip_theme(stage, tdir.name, "scalable", a.out, "svg", "svg"))
            if a.png:
                zips.append(zip_theme(stage, tdir.name, "512", a.out, "png-512", "png"))

    sums = "".join(f"{hashlib.sha256(z.read_bytes()).hexdigest()}  {z.name}\n" for z in zips)
    (a.out / "SHA256SUMS.txt").write_text(sums)
    notes = (f"# Yaru folder icons {a.tag}\n\n"
             f"Folder icons with symbols for {len(zips)} archives "
             f"({'SVG + PNG 512' if a.png else 'SVG'}), one archive per Yaru variant.\n\n"
             "Pick the archive that matches your Yaru variant, unpack it and apply an icon:\n\n"
             "```\ngio set ~/Music metadata::custom-icon file://$HOME/icons/audio-x-generic.svg\n```\n\n"
             "To make your own, use [Folder Symbols](https://github.com/VladyslavChernyshov/folder-symbols).\n\n"
             "Licence: CC BY-SA 4.0 (derivative of Yaru).\n")
    (a.out / "RELEASE_NOTES.md").write_text(notes)
    total = sum(z.stat().st_size for z in zips) / 1e6
    print(f"{len(zips)} archives, {total:.0f} MB -> {a.out}")


if __name__ == "__main__":
    main()
