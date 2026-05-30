"""State files for deduplication and provider cursors."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Set


def load_seen_timestamps(path: Path) -> Dict[str, Set[str]]:
    """Load legacy Apple timestamp dedup state."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return {k: set(v) for k, v in data.items()}
    except (json.JSONDecodeError, OSError):
        return {}


def save_seen_timestamps(path: Path, seen: Dict[str, Set[str]]) -> None:
    """Persist legacy Apple timestamp dedup state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {k: sorted(list(v)) for k, v in seen.items()}
    path.write_text(json.dumps(serializable, indent=2))


def load_seen_versions(path: Path) -> Dict[str, Dict[str, Set[str]]]:
    """Load all seen versions for provider records that can change."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    versions: Dict[str, Dict[str, Set[str]]] = {}
    for source, records in data.items():
        if not isinstance(records, dict):
            continue
        source_versions: Dict[str, Set[str]] = {}
        for record_id, value in records.items():
            if isinstance(value, list):
                source_versions[str(record_id)] = {str(version) for version in value}
            elif value is None:
                source_versions[str(record_id)] = set()
            else:
                source_versions[str(record_id)] = {str(value)}
        versions[source] = source_versions
    return versions


def save_seen_versions(path: Path, seen: Dict[str, Dict[str, Set[str]]]) -> None:
    """Persist version-aware dedup state as source -> record_id -> seen versions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = {
        source: {record_id: sorted(list(versions)) for record_id, versions in records.items()}
        for source, records in seen.items()
    }
    path.write_text(json.dumps(serializable, indent=2, sort_keys=True))
