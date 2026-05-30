"""Filesystem paths used by the local HealthSync collector."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HealthSyncPaths:
    icloud_dir: Path
    desktop_dir: Path
    config_dir: Path
    config_file: Path
    oura_tokens_file: Path
    observations_log: Path
    observations_md: Path
    raw_records_log: Path
    daily_aggregation_md: Path
    legacy_raw_log: Path
    state_dir: Path
    seen_timestamps_file: Path
    seen_versions_file: Path


def default_paths(home: Path | None = None) -> HealthSyncPaths:
    home = home or Path.home()
    desktop_dir = home / "Desktop/HealthSync"
    state_dir = desktop_dir / ".state"
    config_dir = home / ".healthsync"
    return HealthSyncPaths(
        icloud_dir=home / "Library/Mobile Documents/com~apple~CloudDocs/HealthSync",
        desktop_dir=desktop_dir,
        config_dir=config_dir,
        config_file=config_dir / "config.json",
        oura_tokens_file=config_dir / "oura_tokens.json",
        observations_log=desktop_dir / "observations.jsonl",
        observations_md=desktop_dir / "observations.md",
        raw_records_log=desktop_dir / "raw_records.jsonl",
        daily_aggregation_md=desktop_dir / "daily_aggregation.md",
        legacy_raw_log=desktop_dir / "raw_log.md",
        state_dir=state_dir,
        seen_timestamps_file=state_dir / "seen_timestamps.json",
        seen_versions_file=state_dir / "seen_versions.json",
    )


def ensure_output_dirs(paths: HealthSyncPaths) -> None:
    """Create local output, state, and config directories."""
    paths.desktop_dir.mkdir(parents=True, exist_ok=True)
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.config_dir.mkdir(parents=True, exist_ok=True)
