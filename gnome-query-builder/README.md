# GNOME Query Builder (MVP spike)

**Product name:** TBD. Clean-room **GTK4 + libadwaita** app for visually joining Databricks **Unity Catalog** tables, always showing **Spark SQL**, and running limited queries on a **SQL warehouse**.

SQLeo (Java/Swing in the repo root) is **UX inspiration only** — this tree does not fork or reuse SQLeo code.

## Stack choice

| Option | Verdict for this environment |
|--------|------------------------------|
| **Python 3 + PyGObject (Gtk 4 / Adw)** | **Chosen.** `gir1.2-gtk-4.0` + `gir1.2-adw-1` + Meson install cleanly; fast iteration for an integration spike. |
| Rust gtk-rs / relm4 | Viable later; longer compile times and extra crate setup. Not required to prove the path. |

Build/install uses **Meson** (native packaging first). Flatpak is intentionally deferred.

## Features in this spike

1. Adwaita application window + header bar  
2. Databricks backend seam: **CLI profile / SDK** when credentials exist, else **mock UC metadata** so the UI works offline (`--mock`)  
3. Browse UC: catalog → schema → table  
4. **Join canvas** (GtkDrawingArea): table nodes, join edges with type/keys; drag nodes; edit selected edge  
5. Emit Spark SQL with explicit `JOIN`s and `` `catalog`.`schema`.`table` `` names  
6. Run on a SQL warehouse with a **LIMIT** guardrail (mock runner offline)  
7. Save / load local `.sql` files  

## Dependencies (Debian/Ubuntu)

```bash
sudo apt install \
  python3 python3-gi python3-gi-cairo \
  gir1.2-gtk-4.0 gir1.2-adw-1 \
  libgtk-4-dev libadwaita-1-dev \
  meson ninja-build
```

Optional (real workspace calls):

```bash
pip install --user 'databricks-sdk>=0.30'
# plus a working CLI profile, e.g. `databricks auth login --profile DEFAULT`
```

## Run (development)

```bash
cd gnome-query-builder
./scripts/run.sh --mock
# or: PYTHONPATH=src python3 -m gnome_query_builder --mock
```

Useful flags:

| Flag | Meaning |
|------|---------|
| `--mock` | Force offline mock UC + fake warehouse |
| `--profile NAME` | Databricks CLI profile (also `DATABRICKS_CONFIG_PROFILE`) |
| `--limit N` | Default LIMIT spin value |

Without `--mock`, the app uses the SDK when `~/.databrickscfg` or `DATABRICKS_HOST` + token/OAuth env is present; otherwise it falls back to mock with a clear status subtitle.

## Meson install (native)

```bash
cd gnome-query-builder
meson setup build
meson compile -C build
meson install -C build   # may need --prefix=$HOME/.local
gnome-query-builder --mock
```

Install layout:

- `bindir/gnome-query-builder` — launcher script  
- Python package under the interpreter’s site-packages  
- `share/applications/dev.gnomequerybuilder.App.desktop`  

## Native packaging notes (not Flatpak-first)

- Prefer a **`.deb`** (or distro package) that depends on system `gir1.2-gtk-4.0`, `gir1.2-adw-1`, and `python3-gi`.  
- Ship the Meson-installed launcher + module; keep `databricks-sdk` as a pip/vendored optional dependency until packaged.  
- Credentials: reuse **Databricks CLI profiles** / OAuth; later wire **libsecret** for tokens — do not require Flatpak portals for MVP.  
- Flatpak remains optional/secondary; sandboxing often fights GNOME + CLI profile access for this workflow.

## Tests

```bash
cd gnome-query-builder
python3 -m unittest discover -s tests -v
```

## Layout

```
gnome-query-builder/
  meson.build
  src/gnome_query_builder/
    application.py / window.py
    databricks/     # Protocol + mock + SDK
    model/          # JoinGraph + Spark SQL emit
    ui/             # JoinCanvas (DrawingArea)
  data/             # .desktop
  scripts/run.sh
  tests/
```

## Real vs mocked

| Path | Real | Mocked |
|------|------|--------|
| UC browse | SDK `catalogs` / `schemas` / `tables` when authed | Synthetic `samples` / `main` catalogs |
| Columns | SDK `tables.get` | Fixed column lists |
| Warehouses | SDK `warehouses.list` | Single “Mock SQL Warehouse” |
| Execute | Statement Execution API + LIMIT | Deterministic fake grid |
| Save/load `.sql` | Always real (local filesystem) | — |
| SQL emit from graph | Always real (local) | — |
