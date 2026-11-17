"""Scenario H1: the About dialog (gui/welcome.py about_dialog, appinfo.about_info), opened through the app.about
action as the menu item does. The fields are read with Adw.AboutDialog's getters and compared with literals
copied from appinfo.py; the Legal section has no getter, so its labels are found by a widget-tree search
(visible as a FALLBACK info line), or the part is NOT VERIFIED."""
import functools
import os

import registry
import ui

scenario = functools.partial(registry.scenario, in_session_run=False)
WEBSITE = "https://github.com/VladyslavChernyshov/folder-symbols"
FIELDS = {
    "application name": "Folder Symbols",
    "application icon": "folder-symbolic",
    "developer name": "Vladyslav Chernyshov",
    "copyright": "© 2026 Vladyslav Chernyshov",
    "website": WEBSITE,
    "issue url": f"{WEBSITE}/issues",
    "comments": "Put Yaru’s symbolic icons on folders, in Yaru’s embossed folder style.",
}
LEGAL_TITLE = "Yaru artwork"
LEGAL_COPYRIGHT = "Yaru project contributors and Canonical Ltd."
LEGAL_URLS = ("https://github.com/ubuntu/yaru", "https://creativecommons.org/licenses/by-sa/4.0/")


@scenario("H1", "About: name, version, developer, MIT, the links and the Legal section 'Yaru artwork'",
          prepare=lambda ctx: [], steps=("window shown", "About opened", "fields", "Legal section", "closed"))
def h1(d):
    import folder_symbols
    from folder_symbols.appinfo import YARU_ARTWORK
    d.step("window shown")
    win = d.wait_window()
    d.step("About opened")
    d.app.activate_action("about", None)
    dialog = ui.visible_dialog(d, "the About dialog")
    d.check("dialog type", type(dialog).__name__, "AboutDialog")
    d.step("fields")
    actual = {
        "application name": dialog.get_application_name(),
        "application icon": dialog.get_application_icon(),
        "developer name": dialog.get_developer_name(),
        "copyright": dialog.get_copyright(),
        "website": dialog.get_website(),
        "issue url": dialog.get_issue_url(),
        "comments": dialog.get_comments(),
    }
    for key, value in FIELDS.items():
        d.check(f"About {key}", actual[key], value)
    d.check("About version is folder_symbols.__version__", dialog.get_version(), folder_symbols.__version__)
    d.check("About license type", dialog.get_license_type(), d.Gtk.License.MIT_X11)
    d.step("Legal section")
    d.info("FALLBACK: the Legal section is read by a widget-tree search of the dialog (Adw.AboutDialog has no "
           "getter for sections added with add_legal_section)")
    labels = [w for w in ui.walk(dialog) if isinstance(w, d.Gtk.Label)]
    titles = [w for w in labels if w.get_label() == LEGAL_TITLE]
    texts = [w for w in labels if YARU_ARTWORK.text in (w.get_label() or "")]
    if not titles or not texts:
        d.not_verified(f"the Legal section's labels were not found in the dialog's widget tree (title found: "
                       f"{bool(titles)}, text found: {bool(texts)}); what the app passes is appinfo.YARU_ARTWORK")
    else:
        text = texts[0]
        d.check("Legal title labels", len(titles), 1)
        d.check("Legal text labels", len(texts), 1)
        d.check("Legal text is shown as markup (links clickable)", text.get_use_markup(), True)
        d.check("Legal text has the copyright", LEGAL_COPYRIGHT in text.get_label(), True)
        d.check("Legal copyright is the app's", YARU_ARTWORK.copyright, LEGAL_COPYRIGHT)
        with open(os.path.join(os.environ["GUI_CHECK_ROOT"], "NOTICE.md"), encoding="utf-8") as f:
            notice = f.read()
        for url in LEGAL_URLS:
            d.check(f"Legal text links {url}", f'<a href="{url}">{url}</a>' in text.get_label(), True)
            d.check(f"NOTICE.md has {url}", url in notice, True)
    d.step("closed")
    ui.dismiss_dialog(d)
    d.check("visible dialog after closing", win.get_visible_dialog(), None)
