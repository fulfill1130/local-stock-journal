from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal, Protocol

from market_data_types import OhlcvBar, ProviderIssue, ProviderResult, Quote


ProviderCapability = Literal["quotes", "history", "etf_holdings"]


class QuoteProvider(Protocol):
    provider_id: str

    def supports(self, instrument_id: str) -> bool:
        ...

    def get_quotes(self, instrument_ids: list[str]) -> ProviderResult[Quote]:
        ...


class HistoryProvider(Protocol):
    provider_id: str

    def supports(self, instrument_id: str, interval: str = "1d") -> bool:
        ...

    def get_daily_bars(self, instrument_id: str, start: date, end: date) -> ProviderResult[OhlcvBar]:
        ...


class EtfHoldingsProvider(Protocol):
    provider_id: str

    def supports(self, ticker: str) -> bool:
        ...

    def load(self, ticker: str) -> ProviderResult[dict[str, Any]]:
        ...

    def parse(self, raw: Any) -> Any:
        ...

    def normalize(self, parsed: Any) -> dict[str, Any]:
        ...

    def validate(self, snapshot: dict[str, Any]) -> tuple[ProviderIssue, ...]:
        ...


@dataclass
class ProviderRegistry:
    quote_providers: dict[str, QuoteProvider] = field(default_factory=dict)
    history_providers: dict[str, HistoryProvider] = field(default_factory=dict)
    etf_holdings_providers: dict[str, EtfHoldingsProvider] = field(default_factory=dict)

    def register_quote_provider(self, provider: QuoteProvider) -> None:
        self._ensure_provider_id(provider.provider_id)
        self.quote_providers[provider.provider_id] = provider

    def register_history_provider(self, provider: HistoryProvider) -> None:
        self._ensure_provider_id(provider.provider_id)
        self.history_providers[provider.provider_id] = provider

    def register_etf_holdings_provider(self, provider: EtfHoldingsProvider) -> None:
        self._ensure_provider_id(provider.provider_id)
        self.etf_holdings_providers[provider.provider_id] = provider

    def providers_for(self, capability: ProviderCapability) -> list[str]:
        if capability == "quotes":
            return list(self.quote_providers)
        if capability == "history":
            return list(self.history_providers)
        if capability == "etf_holdings":
            return list(self.etf_holdings_providers)
        raise ValueError(f"Unknown provider capability: {capability}")

    def quote_provider(self, provider_id: str) -> QuoteProvider | None:
        return self.quote_providers.get(provider_id)

    def history_provider(self, provider_id: str) -> HistoryProvider | None:
        return self.history_providers.get(provider_id)

    def etf_holdings_provider(self, provider_id: str) -> EtfHoldingsProvider | None:
        return self.etf_holdings_providers.get(provider_id)

    def quote_providers_for_instrument(self, instrument_id: str) -> list[QuoteProvider]:
        return [
            provider
            for provider in self.quote_providers.values()
            if provider.supports(instrument_id)
        ]

    def history_providers_for_instrument(self, instrument_id: str, interval: str = "1d") -> list[HistoryProvider]:
        return [
            provider
            for provider in self.history_providers.values()
            if provider.supports(instrument_id, interval)
        ]

    def etf_holdings_providers_for_ticker(self, ticker: str) -> list[EtfHoldingsProvider]:
        return [
            provider
            for provider in self.etf_holdings_providers.values()
            if provider.supports(ticker)
        ]

    def _ensure_provider_id(self, provider_id: str) -> None:
        if not str(provider_id or "").strip():
            raise ValueError("provider_id is required")
