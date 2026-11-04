"""The one settings file of the app (YAML): port, bind address, data folder, parallel jobs,
upload limit. Unknown keys are errors; missing keys take the defaults below."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

SETTINGS_ENV = "BOOK_APP_SETTINGS"
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class SettingsError(ValueError):
    pass


@dataclass
class AppSettings:
    port: int = 8777
    bind_address: str = "127.0.0.1"
    # The office LAN is off unless this is true: PyMuPDF is AGPL, so the owner decides.
    allow_lan: bool = False
    data_folder: str = "app_data"
    max_parallel_jobs: int = 1
    max_upload_bytes: int = 2_000_000_000
    max_profile_bytes: int = 1_000_000
    max_check_zip_bytes: int = 500_000_000
    # Folder holding the layout models (``models--*`` folders); linked as <cache>/huggingface.
    models_folder: str = ""
    # EPUBCheck jar for the ePub QC; empty: $EPUBCHECK_JAR or tools/epubcheck (else "not run").
    epubcheck_jar: str = ""
    converter_workers: int = 1
    # Leave empty for the real converter; tests give a stand-in command.
    converter_command: list[str] = field(default_factory=list)
    base: Path = field(default=Path("."), repr=False)

    @property
    def data_path(self) -> Path:
        p = Path(self.data_folder).expanduser()
        return p if p.is_absolute() else (self.base / p).resolve()

    @property
    def models_path(self) -> Path | None:
        if not self.models_folder:
            return None
        p = Path(self.models_folder).expanduser()
        return p if p.is_absolute() else (self.base / p).resolve()

    def validate(self) -> None:
        if not 1 <= self.port <= 65535:
            raise SettingsError("port must be between 1 and 65535")
        if self.max_parallel_jobs not in (1, 2):
            raise SettingsError("max_parallel_jobs must be 1 or 2")
        if not 0 < self.max_upload_bytes <= 2**53 - 1:
            raise SettingsError("max_upload_bytes must be a positive whole number")
        if self.bind_address not in LOOPBACK and not self.allow_lan:
            raise SettingsError(
                f"bind_address {self.bind_address!r} is not this computer only; "
                "set allow_lan: true to allow the office network"
            )
        if self.converter_workers < 1:
            raise SettingsError("converter_workers must be at least 1")


def load_settings(path: str | Path | None = None) -> AppSettings:
    path = Path(path or os.environ.get(SETTINGS_ENV) or "app_settings.yaml")
    data: dict = {}
    if path.is_file():
        data = yaml.safe_load(path.read_text("utf-8")) or {}
        if not isinstance(data, dict):
            raise SettingsError(f"{path}: the settings are a mapping of names to values")
    known = {f.name for f in fields(AppSettings)} - {"base"}
    unknown = sorted(set(data) - known)
    if unknown:
        raise SettingsError(f"{path}: unknown setting(s): {', '.join(unknown)}")
    settings = AppSettings(**data, base=path.parent.resolve())
    settings.validate()
    return settings
