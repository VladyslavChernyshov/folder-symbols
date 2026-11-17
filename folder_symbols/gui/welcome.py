"""welcome_page(), the window's page when it was opened without folders, and the About dialog."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from folder_symbols.appinfo import WELCOME, about_info
from folder_symbols.gui.header import menu_button

LICENSES = {"MIT": Gtk.License.MIT_X11}


def welcome_page(menu):
    """A normal header bar (the window title, the window buttons as the system lays them out, the main
    menu) over a status page that says how to open the window for a folder. A function, not a subclass:
    Adw.ToolbarView is a final type."""
    header = Adw.HeaderBar()
    header.pack_end(menu_button(menu))
    view = Adw.ToolbarView()
    view.add_top_bar(header)
    view.set_content(Adw.StatusPage(icon_name=WELCOME.icon_name, title=WELCOME.title,
                                    description=WELCOME.description, vexpand=True, name="welcome-status"))
    return view


def about_dialog():
    """The About dialog (Adw.AboutDialog, libadwaita 1.5) filled from appinfo.about_info()."""
    info = about_info()
    dialog = Adw.AboutDialog(
        application_name=info.application_name, application_icon=info.application_icon,
        version=info.version, developer_name=info.developer_name, copyright=info.copyright,
        license_type=LICENSES[info.license], website=info.website, issue_url=info.issue_url,
        comments=info.comments,
    )
    for section in info.legal_sections:
        dialog.add_legal_section(section.title, section.copyright, Gtk.License.CUSTOM, section.text)
    return dialog
