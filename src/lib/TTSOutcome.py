"""Immutable, evidence-based TTS outcomes.

A completed output write loop is not evidence of device drain or human audibility.
Retries are distinct attempts; one line has exactly one terminal result.
"""
from dataclasses import dataclass
from typing import Literal

TTSOutcome = Literal[
    "completed", "cancelled_before_start", "interrupted", "dropped",
    "synthesis_failed", "output_failed", "no_audio", "unknown",
]


@dataclass(frozen=True)
class TTSAttempt:
    attempt_id: str
    outcome: TTSOutcome
    started_at: float
    ended_at: float
    written_bytes: int = 0
    output_drained: bool | None = None
    reason: str = ""


@dataclass(frozen=True)
class TTSResult:
    line_id: str
    outcome: TTSOutcome
    started_at: float
    ended_at: float
    attempts: tuple[TTSAttempt, ...] = ()
    written_bytes: int = 0
    output_drained: bool | None = None
    reason: str = ""

    @property
    def output_written(self) -> bool:
        """All PCM writes returned without an observed failure or cancellation."""
        return self.outcome == "completed" and self.written_bytes > 0
