#!/usr/bin/env python3
"""Extract the 256 px 'folder' artwork from Yaru's folders.svg into assets/folder-template.svg.

Usage: extract_template.py PATH/TO/src/icons/src/fullcolor/accented-full/places/folders.svg OUT.svg
The Yaru artwork is CC BY-SA 4.0 (see NOTICE.md). Colours are left as Yaru's dummy colours
(#00ff03 accent, #008502 dark overlay); yaru-folder-icon.py replaces them per theme variant.
"""
import re, sys
from lxml import etree

SVG = "http://www.w3.org/2000/svg"
INK = "http://www.inkscape.org/namespaces/inkscape"
XL = "http://www.w3.org/1999/xlink"
NS = {"s": SVG, "i": INK}
REGION = (24, 28, 280, 284)          # the 256x256 export area of the sheet


def first_point(d):
    m = re.match(r"\s*[mM]\s*(-?[\d.e+-]+)[ ,]+(-?[\d.e+-]+)", d)
    return (float(m.group(1)), float(m.group(2))) if m else None


def inside(p):
    return p and REGION[0] <= p[0] <= REGION[2] and REGION[1] <= p[1] <= REGION[3]


def prune(el):
    """Drop paths outside the 256 px region, then empty groups."""
    for ch in list(el):
        if not isinstance(ch.tag, str):
            el.remove(ch); continue
        tag = etree.QName(ch).localname
        if tag == "path":
            if not inside(first_point(ch.get("d", ""))):
                el.remove(ch)
        elif tag == "g":
            prune(ch)
            if len(ch) == 0:
                el.remove(ch)
    return el


def clean(el):
    """Remove Inkscape/sodipodi attributes and ids that nothing references."""
    for e in el.iter():
        if not isinstance(e.tag, str):
            continue
        for a in list(e.attrib):
            if a.startswith("{" + INK) or a.startswith("{http://sodipodi"):
                del e.attrib[a]


def main(src, out):
    root = etree.parse(src).getroot()
    layer = root.xpath("//s:g[@i:label='folder (clone source)'][@i:groupmode='layer']", namespaces=NS)[0]
    shape = prune(layer.xpath("s:g[@i:label='Shape']", namespaces=NS)[0])
    text = etree.tostring(shape).decode()
    refs = set(re.findall(r"url\(#([^)]+)\)", text))
    defs_src = root.find("s:defs", NS)
    byid = {e.get("id"): e for e in defs_src.iter() if e.get("id")}
    need, queue = {}, list(refs)
    while queue:                                    # defs referenced (transitively) by the shape
        i = queue.pop()
        if i in need or i not in byid:
            continue
        need[i] = byid[i]
        t = etree.tostring(byid[i]).decode()
        queue += re.findall(r"url\(#([^)]+)\)", t) + re.findall(r'href="#([^"]+)"', t)
    new = etree.Element("{%s}svg" % SVG, nsmap={None: SVG, "xlink": XL})
    new.set("viewBox", "0 0 256 256"); new.set("width", "256"); new.set("height", "256")
    defs = etree.SubElement(new, "{%s}defs" % SVG)
    for i in sorted(need):
        defs.append(need[i])
    marker = etree.SubElement(defs, "{%s}g" % SVG); marker.set("id", "yfi-symbol-defs")
    g = etree.SubElement(new, "{%s}g" % SVG); g.set("transform", "translate(%g,%g)" % (-REGION[0], -REGION[1]))
    g.set("id", "folder")
    g.append(shape)
    clean(new)
    etree.cleanup_namespaces(new)
    data = etree.tostring(new, pretty_print=True, xml_declaration=True, encoding="UTF-8").decode()
    data = data.replace('<g id="yfi-symbol-defs"/>', "<!--SYMBOL-DEFS-->")
    data = data.replace("</svg>", "<!--SYMBOL-LAYERS-->\n</svg>")
    open(out, "w", encoding="utf-8").write(data)
    print(f"{out}: {len(data) // 1024} KiB, {len(need)} defs, {len(shape.xpath('.//s:path', namespaces=NS))} paths")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
