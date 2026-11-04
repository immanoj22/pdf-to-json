# Frontend

The production app is the `book_app` package (`backend/src/book_app/`): a FastAPI server that
serves a single-page app written as plain ES modules (`static/`, no build step, no
dependencies). Start it with `.venv/bin/python -m book_app`; settings are in
`app_settings.yaml`. See `docs/user_guide.md` and `docs/frontend_report.md`.

`frontend_temp/` is the old temporary upload page. It is superseded and kept only for reference.
