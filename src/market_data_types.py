from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar


Freshness = Literal["realtime", "delayed", "end_of_day", "stale", "manual", "unavailable", "unknown"]
IssueSeverity = Literal["info", "warning", "error"]

T = TypeVar("T")


@dataclass(frozen=True)
class ProviderIssue:
    provider_id: str
    code: str
    message: str
    severity: IssueSeverity = "error"
    retryable: bool = False
    instrument_id: str = ""
    source: str = ""
    observed_at: datetime | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _serializable_dict(asdict(self))


@dataclass(frozen=True)
class Quote:
    instrument_id: str
    provider_id: str
    price: float | None
    previous_close: float | None = None
    change: float | None = None
    change_pct: float | None = None
    source_timestamp: datetime | None = None
    fetched_at: datetime | None = None
    freshness: Freshness = "unknown"
    source: str = ""
    currency: str = ""
    issues: tuple[ProviderIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _serializable_dict(asdict(self))


@dataclass(frozen=True)
class OhlcvBar:
    instrument_id: str
    provider_id: str
    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None
    value: float | None = None
    source_timestamp: datetime | None = None
    fetched_at: datetime | None = None
    freshness: Freshness = "end_of_day"
    source: str = ""
    adjusted: bool = False
    issues: tuple[ProviderIssue, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return _serializable_dict(asdict(self))


@dataclass(frozen=True)
class ProviderResult(Generic[T]):
    provider_id: str
    items: tuple[T, ...] = ()
    issues: tuple[ProviderIssue, ...] = ()
    fetched_at: datetime | None = None
    source: str = ""

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def with_issue(self, issue: ProviderIssue) -> ProviderResult[T]:
        return ProviderResult(
            provider_id=self.provider_id,
            items=self.items,
            issues=(*self.issues, issue),
            fetched_at=self.fetched_at,
            source=self.source,
        )

    def to_dict(self) -> dict[str, Any]:
        return _serializable_dict(asdict(self) | {"ok": self.ok})


def _serializable_dict(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_serializable_dict(item) for item in value]
    if isinstance(value, list):
        return [_serializable_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: _serializable_dict(item) for key, item in value.items()}
    return value
