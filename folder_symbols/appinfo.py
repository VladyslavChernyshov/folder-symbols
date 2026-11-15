"""The application's name, the texts of the welcome page (the window opened without folders), the data of
the About dialog, and which page the window shows (no GTK)."""
import dataclasses

from . import __version__

APP_NAME = "Folder Symbols"
WEBSITE = "https://github.com/VladyslavChernyshov/folder-symbols"

EMPTY_PAGE, MAIN_PAGE = "empty", "main"      # the names of the window's two stack pages


@dataclasses.dataclass(frozen=True)
class WelcomeTexts:
    """The status page shown when the window was opened without folders."""
    icon_name: str
    title: str
    description: str


WELCOME = WelcomeTexts(
    icon_name="folder-symbolic",
    title="Choose a folder",
    description="In Files, right-click a folder and choose “Choose Icon…”.",
)


@dataclasses.dataclass(frozen=True)
class LegalSection:
    """An extra licence section of the About dialog (custom licence text)."""
    title: str
    copyright: str
    text: str                    # Pango markup (the dialog shows it as markup): links are <a href>


def _link(url):
    """A Pango markup link that shows the URL itself."""
    return f'<a href="{url}">{url}</a>'


@dataclasses.dataclass(frozen=True)
class AboutInfo:
    application_name: str
    application_icon: str
    version: str
    developer_name: str
    copyright: str
    license: str                 # "MIT"; the GUI maps it to Gtk.License.MIT_X11
    website: str
    issue_url: str
    comments: str
    legal_sections: tuple        # of LegalSection


# Every sentence and owner line below is copied from NOTICE.md (markdown markup removed, the URLs made
# links); a test checks it.
YARU_ARTWORK = LegalSection(
    title="Yaru artwork",
    copyright="Yaru project contributors and Canonical Ltd.",
    text="The folder drawings, folder icons and symbolic icons that this project's templates and generated "
         "files are built from are part of the Yaru theme (" + _link("https://github.com/ubuntu/yaru") + "), "
         "by the Yaru project contributors and Canonical Ltd. Per Yaru's debian/copyright, the icon artwork "
         "(icons/*, Sam Hewitt and contributors) is licensed under Creative Commons Attribution-ShareAlike 4.0 "
         "(" + _link("https://creativecommons.org/licenses/by-sa/4.0/") + ").\n\n"
         "Changes: symbol and folder combined; no endorsement by Yaru, Canonical or the original authors is "
         "implied.",
)


def about_info():
    """The fields of the About dialog."""
    return AboutInfo(
        application_name=APP_NAME,
        application_icon="folder-symbolic",          # until the .deb brings a real app icon
        version=__version__,
        developer_name="Vladyslav Chernyshov",
        copyright="© 2026 Vladyslav Chernyshov",   # as in LICENSE
        license="MIT",
        website=WEBSITE,
        issue_url=f"{WEBSITE}/issues",
        comments="Put Yaru’s symbolic icons on folders, in Yaru’s embossed folder style.",
        legal_sections=(YARU_ARTWORK,),
    )


def page_for(dirs, current=None):
    """The stack page the window shows: MAIN_PAGE once it has folders (and from then on, even without:
    there is no way back to the welcome page), else EMPTY_PAGE. current is the page shown now, or None."""
    return MAIN_PAGE if dirs or current == MAIN_PAGE else EMPTY_PAGE
