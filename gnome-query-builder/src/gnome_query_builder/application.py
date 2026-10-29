# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk  # noqa: E402

from gnome_query_builder import APPLICATION_ID  # noqa: E402
from gnome_query_builder.databricks.base import DatabricksBackend  # noqa: E402
from gnome_query_builder.window import MainWindow  # noqa: E402


class QueryBuilderApplication(Adw.Application):
    def __init__(
        self,
        *,
        backend: DatabricksBackend,
        default_limit: int = 100,
    ) -> None:
        super().__init__(
            application_id=APPLICATION_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self._backend = backend
        self._default_limit = default_limit
        self._window: MainWindow | None = None

    def do_activate(self) -> None:  # noqa: N802 — GObject override
        if self._window is None:
            self._window = MainWindow(
                application=self,
                backend=self._backend,
                default_limit=self._default_limit,
            )
        self._window.present()

    def do_startup(self) -> None:  # noqa: N802
        Adw.Application.do_startup(self)
        self._install_actions()

    def _install_actions(self) -> None:
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<primary>q"])

        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", self._on_about)
        self.add_action(about)

    def _on_about(self, *_args) -> None:
        dialog = Adw.AboutWindow(
            transient_for=self.get_active_window(),
            application_name="GNOME Query Builder",
            application_icon="org.gnome.Calculator",
            developer_name="SQLeo project (clean-room spike)",
            version="0.1.0",
            comments=(
                "GTK4 + libadwaita visual query builder for Databricks Unity Catalog.\n"
                "Product name TBD. SQLeo is UX inspiration only — not a fork."
            ),
            license_type=Gtk.License.APACHE_2_0,
            website="https://github.com/jacobflanagan/SQLeo",
        )
        dialog.present()
