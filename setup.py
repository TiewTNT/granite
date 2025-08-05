from cx_Freeze import setup, Executable

# Dependencies are automatically detected, but it might need
# fine tuning.
build_options = {
        "build_exe": {
            "packages": ["PySide6", "platformdirs"],
            "include_files": ["assets/", "user/"],  # add your folders/files if needed
        }}

base = 'gui'

executables = [
    Executable('main.py', base=base, target_name = 'granite')
]

setup(name='Granite',
      version = '1.0',
      description = 'A simple note app',
      options = build_options,
      executables = executables)
