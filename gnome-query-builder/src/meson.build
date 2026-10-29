python.install_sources(
  'gnome_query_builder/__init__.py',
  'gnome_query_builder/__main__.py',
  'gnome_query_builder/main.py',
  'gnome_query_builder/application.py',
  'gnome_query_builder/window.py',
  subdir: 'gnome_query_builder',
)

python.install_sources(
  'gnome_query_builder/databricks/__init__.py',
  'gnome_query_builder/databricks/base.py',
  'gnome_query_builder/databricks/factory.py',
  'gnome_query_builder/databricks/mock.py',
  'gnome_query_builder/databricks/sdk_client.py',
  subdir: 'gnome_query_builder/databricks',
)

python.install_sources(
  'gnome_query_builder/model/__init__.py',
  'gnome_query_builder/model/join_graph.py',
  'gnome_query_builder/model/sql_emit.py',
  subdir: 'gnome_query_builder/model',
)

python.install_sources(
  'gnome_query_builder/ui/__init__.py',
  'gnome_query_builder/ui/canvas.py',
  subdir: 'gnome_query_builder/ui',
)

configure_file(
  input: 'gnome-query-builder.in',
  output: 'gnome-query-builder',
  configuration: conf,
  install: true,
  install_dir: bindir,
  install_mode: 'rwxr-xr-x',
)
