# SPDX-License-Identifier: Apache-2.0
"""Main Adwaita window: UC browser, join list, SQL pane, results, save/load."""

from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from gnome_query_builder.databricks.base import (  # noqa: E402
    DatabricksBackend,
    TableRef,
)
from gnome_query_builder.model.join_graph import JoinGraph  # noqa: E402
from gnome_query_builder.model.sql_emit import emit_spark_sql  # noqa: E402


class MainWindow(Adw.ApplicationWindow):
    def __init__(
        self,
        *,
        application: Adw.Application,
        backend: DatabricksBackend,
        default_limit: int = 100,
    ) -> None:
        super().__init__(application=application, title="GNOME Query Builder")
        self.set_default_size(1200, 800)

        self._backend = backend
        self._graph = JoinGraph()
        self._default_limit = default_limit
        self._sql_dirty_from_user = False
        self._current_path: Path | None = None
        self._warehouses: list[tuple[str, str]] = []

        self._build_chrome()
        self._build_body()
        self._reload_catalog_tree()
        self._reload_warehouses()
        self._refresh_sql_from_graph()

    # --- chrome -----------------------------------------------------------------

    def _build_chrome(self) -> None:
        self._toast = Adw.ToastOverlay()
        self.set_content(self._toast)

        toolbar_view = Adw.ToolbarView()
        self._toast.set_child(toolbar_view)

        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        title = Adw.WindowTitle(
            title="GNOME Query Builder",
            subtitle=self._backend.status_label,
        )
        header.set_title_widget(title)

        open_btn = Gtk.Button(icon_name="document-open-symbolic", tooltip_text="Open .sql")
        open_btn.connect("clicked", lambda *_: self._on_open())
        header.pack_start(open_btn)

        save_btn = Gtk.Button(icon_name="document-save-symbolic", tooltip_text="Save .sql")
        save_btn.connect("clicked", lambda *_: self._on_save())
        header.pack_start(save_btn)

        self._warehouse_dd = Gtk.DropDown()
        self._warehouse_dd.set_hexpand(False)
        self._warehouse_dd.set_size_request(220, -1)
        header.pack_end(self._warehouse_dd)

        run_btn = Gtk.Button(label="Run")
        run_btn.add_css_class("suggested-action")
        run_btn.connect("clicked", lambda *_: self._on_run())
        header.pack_end(run_btn)

        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu = Gio.Menu()
        menu.append("About", "app.about")
        menu.append("Quit", "app.quit")
        menu_btn.set_menu_model(menu)
        header.pack_end(menu_btn)

        self._body_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        toolbar_view.set_content(self._body_box)

        banner = Adw.Banner(
            title=(
                f"Backend: {self._backend.mode} — "
                "browse UC, add two tables, edit join keys, run with LIMIT, save .sql"
            )
        )
        banner.set_revealed(True)
        self._body_box.append(banner)

    def _build_body(self) -> None:
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_resize_start_child(True)
        paned.set_shrink_start_child(False)
        paned.set_vexpand(True)
        self._body_box.append(paned)

        # Left: catalog tree
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.set_margin_top(8)
        left.set_margin_bottom(8)
        left.set_margin_start(8)
        left.set_margin_end(4)
        left.set_size_request(260, -1)

        left_label = Gtk.Label(label="Unity Catalog", xalign=0.0)
        left_label.add_css_class("heading")
        left.append(left_label)

        # TreeStore + TreeView is enough for the spike; TreeListModel can come later.
        self._tree = Gtk.TreeView()
        self._tree.set_headers_visible(False)
        self._tree.set_vexpand(True)
        self._store = Gtk.TreeStore(str, str, str, str)  # label, kind, catalog, schema/table
        self._tree.set_model(self._store)
        renderer = Gtk.CellRendererText()
        col = Gtk.TreeViewColumn("Object", renderer, text=0)
        self._tree.append_column(col)
        self._tree.connect("row-activated", self._on_tree_activated)

        scroll_tree = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll_tree.set_child(self._tree)
        scroll_tree.add_css_class("card")
        left.append(scroll_tree)

        add_btn = Gtk.Button(label="Add table to graph")
        add_btn.connect("clicked", lambda *_: self._add_selected_table())
        left.append(add_btn)

        paned.set_start_child(left)

        # Right: join graph + SQL + results
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        paned.set_end_child(right)

        vpaned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        vpaned.set_vexpand(True)
        right.append(vpaned)

        mid = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        mid.set_margin_top(8)
        mid.set_margin_start(4)
        mid.set_margin_end(8)
        vpaned.set_start_child(mid)

        graph_label = Gtk.Label(label="Join graph (tables + keys)", xalign=0.0)
        graph_label.add_css_class("heading")
        mid.append(graph_label)

        self._graph_list = Gtk.ListBox()
        self._graph_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._graph_list.add_css_class("boxed-list")
        mid.append(self._graph_list)

        join_label = Gtk.Label(label="Joins", xalign=0.0)
        join_label.add_css_class("heading")
        mid.append(join_label)

        self._join_list = Gtk.ListBox()
        self._join_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._join_list.add_css_class("boxed-list")
        mid.append(self._join_list)

        sql_label = Gtk.Label(label="Spark SQL (editable — source of truth)", xalign=0.0)
        sql_label.add_css_class("heading")
        mid.append(sql_label)

        self._sql_view = Gtk.TextView()
        self._sql_view.set_monospace(True)
        self._sql_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._sql_view.set_top_margin(8)
        self._sql_view.set_bottom_margin(8)
        self._sql_view.set_left_margin(8)
        self._sql_view.set_right_margin(8)
        self._sql_buffer = self._sql_view.get_buffer()
        self._sql_buffer.connect("changed", self._on_sql_edited)

        sql_scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=160)
        sql_scroll.set_child(self._sql_view)
        sql_scroll.add_css_class("card")
        mid.append(sql_scroll)

        sync_btn = Gtk.Button(label="Regenerate SQL from graph")
        sync_btn.connect("clicked", lambda *_: self._refresh_sql_from_graph(force=True))
        mid.append(sync_btn)

        # Results
        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        bottom.set_margin_top(4)
        bottom.set_margin_bottom(8)
        bottom.set_margin_start(4)
        bottom.set_margin_end(8)
        vpaned.set_end_child(bottom)

        self._results_label = Gtk.Label(label="Results", xalign=0.0)
        self._results_label.add_css_class("heading")
        bottom.append(self._results_label)

        self._results_scroll = Gtk.ScrolledWindow(vexpand=True, min_content_height=140)
        # Spike: simple TreeView for results grid
        self._results_view = Gtk.TreeView()
        self._results_scroll.set_child(self._results_view)
        self._results_scroll.add_css_class("card")
        bottom.append(self._results_scroll)

        limit_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        limit_row.append(Gtk.Label(label="LIMIT"))
        self._limit_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self._limit_spin.set_value(self._default_limit)
        limit_row.append(self._limit_spin)
        bottom.append(limit_row)

    # --- catalog ----------------------------------------------------------------

    def _reload_catalog_tree(self) -> None:
        self._store.clear()
        try:
            catalogs = list(self._backend.list_catalogs())
        except Exception as exc:  # noqa: BLE001
            self._toast_msg(f"Catalog list failed: {exc}")
            return

        for catalog in catalogs:
            cat_iter = self._store.append(None, [catalog, "catalog", catalog, ""])
            try:
                schemas = list(self._backend.list_schemas(catalog))
            except Exception as exc:  # noqa: BLE001
                self._store.append(cat_iter, [f"(error: {exc})", "error", catalog, ""])
                continue
            for schema in schemas:
                sch_iter = self._store.append(
                    cat_iter, [schema, "schema", catalog, schema]
                )
                try:
                    tables = list(self._backend.list_tables(catalog, schema))
                except Exception as exc:  # noqa: BLE001
                    self._store.append(
                        sch_iter, [f"(error: {exc})", "error", catalog, schema]
                    )
                    continue
                for t in tables:
                    self._store.append(
                        sch_iter, [t.name, "table", t.catalog, f"{t.schema}/{t.name}"]
                    )

    def _selected_table(self) -> TableRef | None:
        selection = self._tree.get_selection()
        model, it = selection.get_selected()
        if it is None:
            return None
        kind = model.get_value(it, 1)
        if kind != "table":
            return None
        catalog = model.get_value(it, 2)
        schema_table = model.get_value(it, 3)
        schema, name = schema_table.split("/", 1)
        return TableRef(catalog=catalog, schema=schema, name=name)

    def _on_tree_activated(self, _tree, path, _col) -> None:
        it = self._store.get_iter(path)
        if it and self._store.get_value(it, 1) == "table":
            self._add_selected_table()

    def _add_selected_table(self) -> None:
        ref = self._selected_table()
        if ref is None:
            self._toast_msg("Select a table in the catalog tree")
            return
        try:
            cols = [c.name for c in self._backend.list_columns(ref)]
        except Exception as exc:  # noqa: BLE001
            self._toast_msg(f"Columns failed: {exc}")
            cols = []
        gt = self._graph.add_table(ref, columns=cols)
        self._graph.ensure_edge_for_new_table(gt)
        self._rebuild_graph_ui()
        self._refresh_sql_from_graph()
        self._toast_msg(f"Added {ref.fqn} as `{gt.alias}`")

    # --- join graph UI ----------------------------------------------------------

    def _rebuild_graph_ui(self) -> None:
        while (child := self._graph_list.get_first_child()) is not None:
            self._graph_list.remove(child)
        while (child := self._join_list.get_first_child()) is not None:
            self._join_list.remove(child)

        for t in self._graph.tables:
            row = Adw.ActionRow(
                title=t.ref.fqn,
                subtitle=f"alias `{t.alias}` · {len(t.columns)} columns",
            )
            remove = Gtk.Button(icon_name="user-trash-symbolic")
            remove.set_valign(Gtk.Align.CENTER)
            alias = t.alias

            def _rm(_btn, a=alias) -> None:
                self._graph.remove_alias(a)
                self._rebuild_graph_ui()
                self._refresh_sql_from_graph()

            remove.connect("clicked", _rm)
            row.add_suffix(remove)
            self._graph_list.append(row)

        for idx, edge in enumerate(self._graph.edges):
            row = Adw.ActionRow(
                title=f"{edge.join_type} JOIN",
                subtitle=(
                    f"`{edge.left_alias}`.`{edge.left_column}` = "
                    f"`{edge.right_alias}`.`{edge.right_column}`"
                ),
            )
            left_entry = Gtk.Entry()
            left_entry.set_text(edge.left_column)
            left_entry.set_width_chars(12)
            left_entry.set_valign(Gtk.Align.CENTER)
            right_entry = Gtk.Entry()
            right_entry.set_text(edge.right_column)
            right_entry.set_width_chars(12)
            right_entry.set_valign(Gtk.Align.CENTER)

            def _upd_left(entry, i=idx) -> None:
                self._graph.edges[i].left_column = entry.get_text().strip() or "id"
                self._refresh_sql_from_graph()

            def _upd_right(entry, i=idx) -> None:
                self._graph.edges[i].right_column = entry.get_text().strip() or "id"
                self._refresh_sql_from_graph()

            left_entry.connect("changed", _upd_left)
            right_entry.connect("changed", _upd_right)
            row.add_suffix(left_entry)
            row.add_suffix(Gtk.Label(label="="))
            row.add_suffix(right_entry)
            self._join_list.append(row)

        if not self._graph.tables:
            self._graph_list.append(
                Adw.ActionRow(
                    title="No tables yet",
                    subtitle="Double-click a table or use Add table to graph",
                )
            )

    # --- SQL --------------------------------------------------------------------

    def _refresh_sql_from_graph(self, force: bool = False) -> None:
        if self._sql_dirty_from_user and not force:
            return
        sql = emit_spark_sql(self._graph, limit=None)
        self._sql_dirty_from_user = False
        self._sql_buffer.handler_block_by_func(self._on_sql_edited)
        self._sql_buffer.set_text(sql)
        self._sql_buffer.handler_unblock_by_func(self._on_sql_edited)
        self._sql_dirty_from_user = False

    def _on_sql_edited(self, *_args) -> None:
        self._sql_dirty_from_user = True

    def _sql_text(self) -> str:
        start = self._sql_buffer.get_start_iter()
        end = self._sql_buffer.get_end_iter()
        return self._sql_buffer.get_text(start, end, True)

    # --- warehouses / run -------------------------------------------------------

    def _reload_warehouses(self) -> None:
        try:
            self._warehouses = list(self._backend.list_warehouses())
        except Exception as exc:  # noqa: BLE001
            self._warehouses = []
            self._toast_msg(f"Warehouses: {exc}")
        names = [name for _wid, name in self._warehouses] or ["(no warehouse)"]
        model = Gtk.StringList.new(names)
        self._warehouse_dd.set_model(model)
        if self._warehouses:
            self._warehouse_dd.set_selected(0)

    def _selected_warehouse_id(self) -> str | None:
        if not self._warehouses:
            return None
        idx = self._warehouse_dd.get_selected()
        if idx >= len(self._warehouses):
            return None
        return self._warehouses[idx][0]

    def _on_run(self) -> None:
        sql = self._sql_text().strip()
        if not sql or sql.startswith("--"):
            self._toast_msg("Nothing to run")
            return
        limit = int(self._limit_spin.get_value())
        wid = self._selected_warehouse_id()
        try:
            result = self._backend.execute_sql(sql, warehouse_id=wid, limit=limit)
        except Exception as exc:  # noqa: BLE001
            self._toast_msg(f"Run failed: {exc}")
            return
        self._show_results(result.columns, result.rows)
        self._results_label.set_text(f"Results — {result.message}")
        self._toast_msg(f"Returned {len(result.rows)} row(s)")

    def _show_results(self, columns: list[str], rows: list[list[object]]) -> None:
        if not columns:
            columns = ["(empty)"]
        types = [str] * len(columns)
        store = Gtk.ListStore(*types)
        for row in rows:
            values = [str(row[i]) if i < len(row) else "" for i in range(len(columns))]
            store.append(values)

        # Rebuild columns
        view = self._results_view
        for col in list(view.get_columns()):
            view.remove_column(col)
        view.set_model(store)
        for i, name in enumerate(columns):
            renderer = Gtk.CellRendererText()
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            column = Gtk.TreeViewColumn(name, renderer, text=i)
            column.set_resizable(True)
            view.append_column(column)

    # --- files ------------------------------------------------------------------

    def _on_open(self) -> None:
        dialog = Gtk.FileDialog(title="Open SQL")
        filt = Gtk.FileFilter()
        filt.set_name("SQL files")
        filt.add_pattern("*.sql")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filt)
        dialog.set_filters(filters)

        def _done(dlg, result) -> None:
            try:
                file = dlg.open_finish(result)
            except GLib.Error:
                return
            if file is None:
                return
            path = Path(file.get_path())
            text = path.read_text(encoding="utf-8")
            self._sql_dirty_from_user = True
            self._sql_buffer.set_text(text)
            self._current_path = path
            self._toast_msg(f"Loaded {path.name}")

        dialog.open(self, None, _done)

    def _on_save(self) -> None:
        dialog = Gtk.FileDialog(title="Save SQL")
        if self._current_path:
            dialog.set_initial_name(self._current_path.name)

        def _done(dlg, result) -> None:
            try:
                file = dlg.save_finish(result)
            except GLib.Error:
                return
            if file is None:
                return
            path = Path(file.get_path())
            if path.suffix.lower() != ".sql":
                path = path.with_suffix(".sql")
            path.write_text(self._sql_text(), encoding="utf-8")
            self._current_path = path
            self._toast_msg(f"Saved {path.name}")

        dialog.save(self, None, _done)

    def _toast_msg(self, message: str) -> None:
        self._toast.add_toast(Adw.Toast(title=message, timeout=3))
