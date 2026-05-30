"""Embeddable collection API for HealthSync providers."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from threading import Lock

from .observer import CollectionResult, Observer
from .paths import HealthSyncPaths, default_paths, ensure_output_dirs

LogFn = Callable[[str], None]


def default_observers(paths: HealthSyncPaths) -> list[Observer]:
    """Build the default HealthSync observer set.

    Provider imports are intentionally local so embedders can construct their
    own observer list without importing disabled providers.
    """
    from .providers.apple.shortcut import AppleShortcutObserver
    from .providers.oura.api import OuraObserver

    return [
        AppleShortcutObserver(paths),
        OuraObserver(paths),
    ]


def collect_once(
    observers: Sequence[Observer] | None = None,
    *,
    paths: HealthSyncPaths | None = None,
    lock: Lock | None = None,
    log: LogFn | None = print,
) -> list[CollectionResult]:
    """Collect once from registered observers.

    When observers are omitted, the default Apple Shortcut and Oura observers
    are created from the provided paths or the local default paths.
    """
    if observers is None:
        paths = paths or default_paths()
        ensure_output_dirs(paths)
        observers = default_observers(paths)
    return _collect_with_optional_lock(observers, lock=lock, log=log)


def collected_count(results: Sequence[CollectionResult]) -> int:
    """Return the total number of observations reported by collection results."""
    return sum(result.collected for result in results)


def _collect_with_optional_lock(
    observers: Sequence[Observer],
    *,
    lock: Lock | None,
    log: LogFn | None,
) -> list[CollectionResult]:
    if lock is None:
        return _collect(observers, log=log)
    with lock:
        return _collect(observers, log=log)


def _collect(observers: Sequence[Observer], *, log: LogFn | None) -> list[CollectionResult]:
    results: list[CollectionResult] = []
    for observer in observers:
        try:
            result = observer.collect()
        except Exception as e:
            message = str(e)
            if log:
                log(f"[watcher] {observer.name} failed: {message}")
            result = CollectionResult(observer_name=observer.name, failed=1, message=message)
        results.append(result)

    for result in results:
        if not log:
            continue
        if result.collected:
            log(f"[watcher] appended {result.collected} {result.observer_name} observations")
        if result.skipped:
            log(f"[watcher] skipped {result.skipped} {result.observer_name} records")
        if result.failed:
            detail = f": {result.message}" if result.message else ""
            log(f"[watcher] {result.failed} {result.observer_name} failures{detail}")
    return results
