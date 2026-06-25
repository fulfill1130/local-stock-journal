from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol

from market_data_types import OhlcvBar, ProviderResult, Quote


ProviderCapability = Literal["quotes", "history"]


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


@dataclass
class ProviderRegistry:
    quote_providers: dict[str, QuoteProvider] = field(default_factory=dict)
    history_providers: dict[str, HistoryProvider] = field(default_factory=dict)

    def register_quote_provider(self, provider: QuoteProvider) -> None:
        self._ensure_provider_id(provider.provider_id)
        self.quote_providers[provider.provider_id] = provider

    def register_history_provider(self, provider: HistoryProvider) -> None:
        self._ensure_provider_id(provider.provider_id)
        self.history_providers[provider.provider_id] = provider

    def providers_for(self, capability: ProviderCapability) -> list[str]:
        if capability == "quotes":
            return list(self.quote_providers)
        if capability == "history":
            return list(self.history_providers)
        raise ValueError(f"Unknown provider capability: {capability}")

    def quote_provider(self, provider_id: str) -> QuoteProvider | None:
        return self.quote_providers.get(provider_id)

    def history_provider(self, provider_id: str) -> HistoryProvider | None:
        return self.history_providers.get(provider_id)

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

    def _ensure_provider_id(self, provider_id: str) -> None:
        if not str(provider_id or "").strip():
            raise ValueError("provider_id is required")
