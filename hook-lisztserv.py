from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = collect_submodules('lisztserv')

# Collect all data files (including frontend templates and static files)
datas = collect_data_files('lisztserv', include_py_files=True) 