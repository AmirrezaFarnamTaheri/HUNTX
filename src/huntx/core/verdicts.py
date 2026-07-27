from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class VerdictStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    EXPIRED = "expired"


@dataclass(frozen=True)
class SyntaxVerdict:
    status: VerdictStatus
    parser_version: str
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProbeVerdict:
    status: VerdictStatus
    checked_at: datetime
    expires_at: datetime
    latency_ms: Optional[float] = None
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    def effective_status(self, now: Optional[datetime] = None) -> VerdictStatus:
        current = now or datetime.now(timezone.utc)
        if current >= self.expires_at:
            return VerdictStatus.EXPIRED
        return self.status


@dataclass(frozen=True)
class PolicyVerdict:
    status: VerdictStatus
    policy_version: str
    tier: str
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PublicationDecision:
    syntax: SyntaxVerdict
    probe: ProbeVerdict
    policy: PolicyVerdict

    def is_eligible(self, *, require_fresh_probe: bool = True) -> bool:
        if self.syntax.status != VerdictStatus.PASS:
            return False
        if self.policy.status != VerdictStatus.PASS:
            return False
        probe_status = self.probe.effective_status()
        if require_fresh_probe and probe_status != VerdictStatus.PASS:
            return False
        return probe_status not in {VerdictStatus.FAIL, VerdictStatus.EXPIRED}
