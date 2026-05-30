"""Mac delivery runtime for the local HealthSync watcher."""
from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from pathlib import Path
from threading import Lock

from ..observer import Observer
from ..paths import HealthSyncPaths, default_paths, ensure_output_dirs
from ..collection import collect_once, default_observers
from ..daily_aggregation import write_daily_aggregation

LogFn = Callable[[str], None]


def poll_forever(
    observers: Sequence[Observer] | None = None,
    *,
    paths: HealthSyncPaths | None = None,
    lock: Lock | None = None,
    log: LogFn | None = print,
) -> None:
    """Start the local Mac watcher loop. Runs until interrupted."""
    paths = paths or default_paths()
    ensure_output_dirs(paths)
    observers = list(observers or default_observers(paths))
    lock = lock or Lock()
    log = log or (lambda _message: None)

    log(f"[watcher] watching {paths.icloud_dir}")
    log(f"[watcher] outputs at {paths.desktop_dir}")

    if not paths.icloud_dir.exists():
        log(
            f"[watcher] WARNING: {paths.icloud_dir} does not exist yet. "
            "It will be populated the first time the iOS Shortcut runs."
        )
        paths.icloud_dir.mkdir(parents=True, exist_ok=True)

    collect_once(observers, paths=paths, lock=lock, log=log)
    refresh_daily_aggregation(paths, log)

    from watchdog.observers import Observer as WatchdogObserver

    filesystem_observer = WatchdogObserver()
    filesystem_observer.schedule(
        HealthSyncHandler(observers=observers, paths=paths, lock=lock, log=log),
        str(paths.icloud_dir),
        recursive=False,
    )
    filesystem_observer.start()
    poller = PeriodicPoller(observers=observers, paths=paths, lock=lock, log=log)
    if poller.has_observers:
        log(f"[watcher] polling periodic observers every {poller.describe_intervals()}")
    try:
        while True:
            poller.maybe_process()
            time.sleep(1)
    except KeyboardInterrupt:
        filesystem_observer.stop()
    filesystem_observer.join()


class PeriodicPoller:
    """Poll observers that declare a poll_interval_seconds method."""

    def __init__(self, *, observers: Sequence[Observer], paths: HealthSyncPaths, lock: Lock, log: LogFn) -> None:
        self.lock = lock
        self.log = log
        self.paths = paths
        self._entries: list[dict] = []
        for observer in observers:
            interval = observer_poll_interval(observer)
            if interval is None:
                continue
            self._entries.append(
                {
                    "observer": observer,
                    "interval": interval,
                    "next_run": time.monotonic() + interval,
                }
            )

    @property
    def has_observers(self) -> bool:
        return bool(self._entries)

    def describe_intervals(self) -> str:
        return ", ".join(
            f"{entry['observer'].name}: {entry['interval']} seconds"
            for entry in self._entries
        )

    def maybe_process(self) -> None:
        now = time.monotonic()
        for entry in self._entries:
            if now < entry["next_run"]:
                continue
            observer = entry["observer"]
            try:
                collect_once([observer], lock=self.lock, log=self.log)
                refresh_daily_aggregation(self.paths, self.log)
            except Exception as e:
                self.log(f"[watcher] error polling {observer.name}: {e}")
            finally:
                interval = observer_poll_interval(observer) or entry["interval"]
                entry["interval"] = interval
                entry["next_run"] = time.monotonic() + interval


class HealthSyncHandler:
    """Watchdog handler that collects source-file observers on change."""

    def __init__(self, *, observers: Sequence[Observer], paths: HealthSyncPaths, lock: Lock, log: LogFn) -> None:
        self.observers = list(observers)
        self.paths = paths
        self.lock = lock
        self.log = log
        self.last_run = 0.0

    def dispatch(self, event) -> None:
        if getattr(event, "event_type", None) == "modified":
            self.on_modified(event)
        elif getattr(event, "event_type", None) == "created":
            self.on_created(event)

    def _maybe_process(self, event) -> None:
        if event.is_directory:
            return
        source_path = Path(event.src_path)
        observers = observers_for_filename(self.observers, source_path.name)
        if not observers:
            return

        now = time.time()
        if now - self.last_run < 2.0:
            return
        self.last_run = now

        time.sleep(1.0)
        try:
            collect_once(observers, lock=self.lock, log=self.log)
            refresh_daily_aggregation(self.paths, self.log)
        except Exception as e:
            self.log(f"[watcher] error processing: {e}")

    def on_modified(self, event) -> None:
        self._maybe_process(event)

    def on_created(self, event) -> None:
        self._maybe_process(event)


def observers_for_filename(observers: Sequence[Observer], filename: str) -> list[Observer]:
    """Return observers that watch a given source filename."""
    return [
        observer
        for observer in observers
        if filename in tuple(getattr(observer, "source_filenames", ()))
    ]


def observer_poll_interval(observer: Observer) -> int | None:
    poll_interval_seconds = getattr(observer, "poll_interval_seconds", None)
    if not callable(poll_interval_seconds):
        return None
    try:
        return max(int(poll_interval_seconds()), 1)
    except Exception:
        return None


def refresh_daily_aggregation(paths: HealthSyncPaths, log: LogFn) -> None:
    try:
        write_daily_aggregation(paths)
    except Exception as e:
        log(f"[watcher] daily aggregation failed: {e}")


def main() -> None:
    """Start the local Mac watcher loop. Runs until interrupted."""
    poll_forever()


if __name__ == "__main__":
    main()
