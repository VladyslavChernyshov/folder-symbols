"""FolderSymbolsWindow: Adw.ApplicationWindow subclass."""
import os
import sys
import traceback

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk

from folder_symbols.apply import ApplyError, RecordError, apply_folders, reset_folders
from folder_symbols.gallery import list_symbols
from folder_symbols.initial import initial_state, read_manifest, recorded_folders
from folder_symbols.outcome import (apply_block_reason, apply_outcome, apply_tooltip, reset_button_state,
                                    reset_confirmation, reset_outcome)
from folder_symbols.store import ManifestError
from folder_symbols.symbols import default_symbols_dir
from folder_symbols.gui.gallery import SymbolGallery
from folder_symbols.gui.header import FolderHeader, GalleryHeader
from folder_symbols.gui.preview import PreviewPanel

APP_TITLE = "Folder Symbols"
DEFAULT_SIZE = (850, 600)                # mockup .win
SIDEBAR_WIDTH_FRACTION = 0.32            # about 270 px at 850 px (mockup .right)
SIDEBAR_MIN_WIDTH = 220
SIDEBAR_MAX_WIDTH = 300
DETAILS_MAX_HEIGHT = 240                 # folder lists in the dialogs scroll above this height


class FolderSymbolsWindow(Adw.ApplicationWindow):
    # The gallery.Symbol selected in the gallery, or None.
    selected_symbol = GObject.Property(type=GObject.TYPE_PYOBJECT, nick="selected-symbol")

    def __init__(self, preview_session, apply_func=apply_folders, reset_func=reset_folders, **kwargs):
        """apply_func, reset_func: what Apply and Reset call, apply.apply_folders and apply.reset_folders
        by default (stubs in tests and self-checks)."""
        super().__init__(title=APP_TITLE, **kwargs)
        self._preview_session = preview_session
        self._apply_func, self._reset_func = apply_func, reset_func
        self._dirs, self._recorded, self._busy = [], [], False
        self._symbols_dir = default_symbols_dir()
        self._symbols, self._gallery_header, self._gallery = [], None, None
        self.set_default_size(*DEFAULT_SIZE)

        # Nautilus-style split (Adw.OverlaySplitView, libadwaita >= 1.4): the gallery on the left, the
        # preview sidebar on the right, never collapsed. Each pane has its own flat header bar, so the
        # gallery's header has the window's colour and the sidebar's the sidebar colour. Each header bar
        # shows only the window buttons on its window-edge side.
        self._folder_header = FolderHeader()
        self._panel = PreviewPanel(self._preview_session)
        self.connect("notify::selected-symbol", lambda *_: self._on_symbol())
        self._panel.apply_button.connect("clicked", lambda *_: self._on_apply())
        self._panel.reset_button.connect("clicked", lambda *_: self._on_reset())
        self._update_buttons()
        sidebar = Adw.ToolbarView()
        sidebar.add_top_bar(self._folder_header)
        sidebar.set_content(self._panel)

        split = Adw.OverlaySplitView(
            sidebar_position=Gtk.PackType.END, collapsed=False, show_sidebar=True,
            sidebar_width_fraction=SIDEBAR_WIDTH_FRACTION,
            min_sidebar_width=SIDEBAR_MIN_WIDTH, max_sidebar_width=SIDEBAR_MAX_WIDTH,
            content=self._build_content(self._symbols_dir), sidebar=sidebar,
        )
        self.set_content(split)

    def _build_content(self, symbols_dir):
        """The gallery pane: its header bar over the symbol grid, or over a status page when symbols_dir
        has no symbols. The divider under the header while the grid is scrolled is the ToolbarView's."""
        symbols, problem = self._load_symbols(symbols_dir)
        header = self._gallery_header = GalleryHeader(symbols)
        header.search.set_key_capture_widget(self)      # typing anywhere in the window starts the search
        view = Adw.ToolbarView()
        view.add_top_bar(header)
        if problem:
            view.set_content(self._no_symbols(problem))
            return view
        self._symbols = symbols
        gallery = self._gallery = SymbolGallery(symbols)
        gallery.bind_property("selected-symbol", self, "selected-symbol", GObject.BindingFlags.SYNC_CREATE)
        update = lambda *_: gallery.set_filter(header.query, header.category or None)
        header.connect("notify::query", update)
        header.connect("notify::category", update)
        view.set_content(gallery)
        return view

    @staticmethod
    def _load_symbols(symbols_dir):
        """Return (symbols, problem); problem is a message when there is nothing to show."""
        if not os.path.isdir(symbols_dir):
            return [], f"Folder does not exist: {symbols_dir}"
        try:
            symbols = list_symbols(symbols_dir)
        except OSError as e:
            return [], f"Cannot read {symbols_dir}: {e.strerror or e}"
        if not symbols:
            return [], f"No *-symbolic.svg files in {symbols_dir}"
        return symbols, None

    @staticmethod
    def _no_symbols(reason):
        return Adw.StatusPage(
            title="Symbols not found",
            description=f"{reason}\n\nInstall yaru-theme-icon or point YARU_SYMBOLS_DIR at a folder with "
                        "*-symbolic.svg files.",
            icon_name="dialog-warning-symbolic",
            vexpand=True,
        )

    def update_selection(self, dirs, total):
        """Show a new folder selection: the sidebar header's title and tooltip, and the initial state from
        the manifest (read only): the recorded symbol selected and scrolled to, previewed in the recorded
        accent, or nothing selected. The search and the category are reset first, so the symbol can be
        shown even when the previous filter would hide it."""
        self._folder_header.set_selection(dirs, total)
        self._dirs = list(dirs)
        manifest, problem = read_manifest()
        self._recorded = recorded_folders(self._dirs, manifest)
        self._update_buttons()
        if self._gallery is None:                         # no symbols: only the status page
            return
        state = initial_state(dirs, manifest, self._symbols, self._symbols_dir)
        for line in (problem, state.message):
            if line:
                print(line, file=sys.stderr)
        self._gallery_header.reset_filter()
        self._panel.set_initial_accent(state.accent)
        self._gallery.select_symbol(state.symbol)

    # ------------------------------------------------------------- Apply and Reset
    def _on_symbol(self):
        self._panel.set_symbol(self.selected_symbol)
        self._update_buttons()

    def _update_buttons(self):
        reason = apply_block_reason(self.selected_symbol is not None, len(self._dirs), self._busy)
        button = self._panel.apply_button
        button.set_sensitive(reason is None)
        button.set_tooltip_text(reason or apply_tooltip(len(self._dirs)))
        label, sensitive, tooltip = reset_button_state(len(self._dirs), len(self._recorded), self._busy)
        button = self._panel.reset_button
        button.set_label(label)
        button.set_sensitive(sensitive)
        button.set_tooltip_text(tooltip)

    def _on_apply(self):
        """Apply what the panel shows now to the selected folders: close on success, else a dialog. The
        choice and the folders are frozen at the click; the call is synchronous."""
        choice, dirs = self._panel.current_choice(), tuple(self._dirs)
        if self._busy or choice.symbol is None or not dirs:
            return
        self._run(lambda: self._apply_func(list(dirs), choice.symbol.name, choice.accent, dark=choice.dark,
                                           system_accent=choice.system_accent, symbols_dir=self._symbols_dir),
                  apply_outcome)

    def _on_reset(self):
        """Reset the selected folders that have a manifest entry, frozen at the click: one at once, several
        after a confirmation. Close on success, else a dialog."""
        targets = tuple(self._recorded)
        if self._busy or not targets:
            return
        if len(targets) == 1:
            self._reset(targets)
            return
        heading, body, details = reset_confirmation(targets)
        dialog = Adw.AlertDialog(heading=heading, body=body)
        dialog.set_extra_child(self._details(details))
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", lambda _d, response: response == "reset" and self._reset(targets))
        dialog.present(self)

    def _reset(self, targets):
        self._run(lambda: self._reset_func(list(targets)), reset_outcome)

    def _run(self, call, outcome_of):
        """Run call() (synchronously) with both buttons blocked, then close the window if every folder was
        done, else re-read which selected folders have an entry and show the outcome dialog."""
        self._busy = True
        self._update_buttons()
        try:
            results = call()
        except Exception as e:                            # every failure ends in a dialog, never a crash
            if not isinstance(e, (ManifestError, ApplyError, RecordError)):
                traceback.print_exc()                     # unexpected: keep the details for a bug report
            outcome = outcome_of(error=e)
        else:
            outcome = outcome_of(results=results)
        finally:
            self._busy = False
        if outcome.close:
            self.close()
            return
        manifest, _problem = read_manifest()              # the entries may have changed: recount for Reset
        self._recorded = recorded_folders(self._dirs, manifest)
        self._update_buttons()
        self._show_outcome(outcome)

    @staticmethod
    def _details(text):
        # selectable for copying with the mouse, but not focusable: it would take the focus from the
        # buttons and show all its text selected when the dialog opens
        label = Gtk.Label(label=text, xalign=0, wrap=True, selectable=True, focusable=False,
                          css_classes=["caption"])
        return Gtk.ScrolledWindow(child=label, propagate_natural_height=True,
                                  max_content_height=DETAILS_MAX_HEIGHT, hscrollbar_policy=Gtk.PolicyType.NEVER)

    def _show_outcome(self, outcome):
        dialog = Adw.AlertDialog(heading=outcome.title, body=outcome.body)
        if outcome.details:
            dialog.set_extra_child(self._details(outcome.details))
        if outcome.close_button:
            dialog.add_response("close", "Close Window")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        dialog.connect("response", lambda _d, response: response == "close" and self.close())
        dialog.present(self)
