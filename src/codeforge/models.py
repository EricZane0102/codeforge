"""Data models for CodeForge.

Defines the core data structures: Challenge (from YAML), Session state,
ReviewResult, and StatsRecord.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class Difficulty(str, Enum):
    """Challenge difficulty levels."""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class SessionStatus(str, Enum):
    """Status of a challenge session."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    REVIEWED = "reviewed"


@dataclass
class ChallengeSetup:
    """Git setup info for a challenge."""
    base_commit: str
    solution_commit: str
    test_command: str = ""
    files_of_interest: list[str] = field(default_factory=list)


@dataclass
class Challenge:
    """A coding challenge loaded from YAML."""
    id: str
    title: str
    repo: str
    difficulty: Difficulty
    time_limit: int  # minutes
    description: str
    setup: ChallengeSetup
    tags: list[str] = field(default_factory=list)
    hints: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Challenge:
        """Create a Challenge from a YAML-parsed dictionary."""
        setup_data = data.get("setup", {})
        setup = ChallengeSetup(
            base_commit=setup_data.get("base_commit", ""),
            solution_commit=setup_data.get("solution_commit", ""),
            test_command=setup_data.get("test_command", ""),
            files_of_interest=setup_data.get("files_of_interest", []),
        )
        return cls(
            id=data["id"],
            title=data["title"],
            repo=data["repo"],
            difficulty=Difficulty(data["difficulty"]),
            time_limit=data.get("time_limit", 30),
            description=data.get("description", ""),
            setup=setup,
            tags=data.get("tags", []),
            hints=data.get("hints", []),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return asdict(self)


@dataclass
class ReviewScore:
    """Five-dimension review scores."""
    correctness: int = 0
    approach: int = 0
    code_quality: int = 0
    edge_cases: int = 0
    thinking_quality: int = 0
    feedback: str = ""

    @property
    def average(self) -> float:
        """Calculate the average score across all dimensions."""
        scores = [
            self.correctness,
            self.approach,
            self.code_quality,
            self.edge_cases,
            self.thinking_quality,
        ]
        return sum(scores) / len(scores) if scores else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewScore:
        """Create from a dictionary."""
        return cls(
            correctness=data.get("correctness", 0),
            approach=data.get("approach", 0),
            code_quality=data.get("code_quality", 0),
            edge_cases=data.get("edge_cases", 0),
            thinking_quality=data.get("thinking_quality", 0),
            feedback=data.get("feedback", ""),
        )


@dataclass
class Session:
    """State for a single challenge attempt."""
    challenge_id: str
    status: SessionStatus = SessionStatus.NOT_STARTED
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    hints_used: list[int] = field(default_factory=list)
    test_passed: Optional[bool] = None
    test_output: str = ""
    user_diff: str = ""
    solution_diff: str = ""
    review: Optional[ReviewScore] = None
    retro: Optional[dict] = None

    def start(self) -> None:
        """Mark session as started."""
        self.status = SessionStatus.IN_PROGRESS
        self.start_time = datetime.now().isoformat()

    def submit(self) -> None:
        """Mark session as submitted."""
        self.status = SessionStatus.SUBMITTED
        self.end_time = datetime.now().isoformat()

    @property
    def elapsed_minutes(self) -> Optional[float]:
        """Calculate elapsed time in minutes."""
        if not self.start_time:
            return None
        start = datetime.fromisoformat(self.start_time)
        end = datetime.fromisoformat(self.end_time) if self.end_time else datetime.now()
        return (end - start).total_seconds() / 60

    def save(self, path: Path) -> None:
        """Save session state to a JSON file."""
        data = {
            "challenge_id": self.challenge_id,
            "status": self.status.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "hints_used": self.hints_used,
            "test_passed": self.test_passed,
            "test_output": self.test_output,
            "user_diff": self.user_diff,
            "solution_diff": self.solution_diff,
            "review": self.review.to_dict() if self.review else None,
            "retro": self.retro,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path) -> Session:
        """Load session state from a JSON file."""
        data = json.loads(path.read_text())
        review_data = data.get("review")
        return cls(
            challenge_id=data["challenge_id"],
            status=SessionStatus(data.get("status", "not_started")),
            start_time=data.get("start_time"),
            end_time=data.get("end_time"),
            hints_used=data.get("hints_used", []),
            test_passed=data.get("test_passed"),
            test_output=data.get("test_output", ""),
            user_diff=data.get("user_diff", ""),
            solution_diff=data.get("solution_diff", ""),
            review=ReviewScore.from_dict(review_data) if review_data else None,
            retro=data.get("retro"),
        )
