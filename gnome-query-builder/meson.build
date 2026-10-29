project(
  'gnome-query-builder',
  version: '0.1.0',
  meson_version: '>= 0.61.0',
  license: 'Apache-2.0',
)

python = import('python').find_installation('python3', modules: ['gi'])

# Runtime GI namespaces (checked at configure time when available).
dependency('gtk4', version: '>= 4.10', required: false)
dependency('libadwaita-1', version: '>= 1.4', required: false)

prefix = get_option('prefix')
bindir = join_paths(prefix, get_option('bindir'))
datadir = join_paths(prefix, get_option('datadir'))
pkgdatadir = join_paths(datadir, meson.project_name())
pythondir = python.get_install_dir()

conf = configuration_data()
conf.set('PYTHON', python.full_path())
conf.set('localedir', join_paths(prefix, get_option('localedir')))
conf.set('pkgdatadir', pkgdatadir)
conf.set('VERSION', meson.project_version())
conf.set('APPLICATION_ID', 'dev.gnomequerybuilder.App')

subdir('data')
subdir('src')

summary({
  'prefix': prefix,
  'python': python.full_path(),
  'bindir': bindir,
}, section: 'Directories')
