from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass(frozen=True)
class WordSet:
    id: int
    name: str

    @property
    def label(self) -> str:
        return f"{self.name} (id: {self.id})"


class WordAction(str, Enum):
    ADDED = "added"
    UPDATED = "updated"
    ALREADY_OK = "already_ok"
    FAILED = "failed"


@dataclass(frozen=True)
class WordEntry:
    word: str
    definition: str


@dataclass
class Verification:
    exact_word: bool = False
    combined_translation: bool = False
    learning_status: bool = False
    progress: bool = False
    word_set: bool = False

    @property
    def ok(self) -> bool:
        return (
            self.exact_word
            and self.combined_translation
            and self.learning_status
            and self.progress
            and self.word_set
        )


@dataclass
class WordResult:
    entry: WordEntry
    action: WordAction
    word_id: int | None = None
    disabled_translations: int = 0
    verification: Verification = field(default_factory=Verification)
    error: str | None = None
    raw_word: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.action != WordAction.FAILED and self.verification.ok


@dataclass
class BatchReport:
    results: list[WordResult]

    @property
    def added(self) -> list[WordResult]:
        return [item for item in self.results if item.ok and item.action == WordAction.ADDED]

    @property
    def updated(self) -> list[WordResult]:
        return [item for item in self.results if item.ok and item.action == WordAction.UPDATED]

    @property
    def already_ok(self) -> list[WordResult]:
        return [item for item in self.results if item.ok and item.action == WordAction.ALREADY_OK]

    @property
    def failed(self) -> list[WordResult]:
        return [item for item in self.results if not item.ok]

    @property
    def reset_status_count(self) -> int:
        return len([item for item in self.results if item.ok])
