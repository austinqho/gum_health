from __future__ import annotations

from health_observer.collection import collect_once
from health_observer.observer import CollectionResult


class FailingObserver:
    name = "failing"

    def collect(self) -> CollectionResult:
        raise RuntimeError("bad source row")


class PassingObserver:
    name = "passing"

    def collect(self) -> CollectionResult:
        return CollectionResult(observer_name=self.name, collected=2)


def test_collect_once_isolates_observer_failures() -> None:
    messages = []

    results = collect_once(
        [FailingObserver(), PassingObserver()],
        log=messages.append,
    )

    assert results == [
        CollectionResult(observer_name="failing", failed=1, message="bad source row"),
        CollectionResult(observer_name="passing", collected=2),
    ]
    assert any("failing failed: bad source row" in message for message in messages)
    assert any("appended 2 passing observations" in message for message in messages)
    assert any("1 failing failures: bad source row" in message for message in messages)


def test_collection_result_reports_collected_skipped_failed() -> None:
    result = CollectionResult(observer_name="apple", collected=3, skipped=1)

    assert result.collected == 3
    assert result.skipped == 1
    assert result.failed == 0
