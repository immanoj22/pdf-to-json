"""Start the app: ``python -m book_app [--settings app_settings.yaml]``."""

from __future__ import annotations

import argparse
import sys

from .config import SettingsError, load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="book-app",
        description="Book Converter: PDF to DocBook, ePub, HTML, NIMAS, DAISY, JATS and BITS",
    )
    parser.add_argument("--settings", help="settings file (default: app_settings.yaml)")
    args = parser.parse_args(argv)
    try:
        settings = load_settings(args.settings)
    except SettingsError as exc:
        print(f"Settings problem: {exc}", file=sys.stderr)
        return 2
    import uvicorn

    from .api import create_app

    app = create_app(settings)
    shown = "127.0.0.1" if settings.bind_address in ("0.0.0.0", "::") else settings.bind_address
    print(f"Book Converter is running at http://{shown}:{settings.port}")
    print(f"Data folder: {settings.data_path}")
    if settings.allow_lan:
        print(
            "WARNING: the office network is allowed. The PDF reader (PyMuPDF) is licensed "
            "AGPL: sharing this app over a network needs its licence checked first.",
            file=sys.stderr,
        )
    # SIGTERM/SIGINT end the server and run the app's shutdown (running conversions are stopped and
    # parked: they resume from their cache at the next start). Open browser connections must not
    # hold the shutdown: after this many seconds they are closed.
    uvicorn.run(
        app, host=settings.bind_address, port=settings.port, log_level="warning",
        timeout_graceful_shutdown=15,
    )  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
