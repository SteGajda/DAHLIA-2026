"""Run DAHLIA from a source checkout or package this file with nicegui-pack."""

from multiprocessing import freeze_support


if __name__ == "__main__":
    # Intercept PyInstaller child processes before NiceGUI/sklearn imports.
    freeze_support()

from dahlia.core.desktop_runtime import configure_desktop_runtime, report_startup_error

try:
    configure_desktop_runtime()
    # Keep native window configuration importable in spawned processes.
    from dahlia.app.main import main

    if __name__ == "__main__":
        main()
except Exception:
    report_startup_error()
    raise SystemExit(1)
