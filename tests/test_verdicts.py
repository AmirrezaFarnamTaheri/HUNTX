from datetime import datetime, timedelta, timezone

from huntx.core.verdicts import (
    PolicyVerdict,
    ProbeVerdict,
    PublicationDecision,
    SyntaxVerdict,
    VerdictStatus,
)


def _decision(
    syntax: VerdictStatus = VerdictStatus.PASS,
    probe: VerdictStatus = VerdictStatus.PASS,
    policy: VerdictStatus = VerdictStatus.PASS,
) -> PublicationDecision:
    now = datetime.now(timezone.utc)
    return PublicationDecision(
        syntax=SyntaxVerdict(status=syntax, parser_version="test"),
        probe=ProbeVerdict(
            status=probe,
            checked_at=now,
            expires_at=now + timedelta(minutes=5),
        ),
        policy=PolicyVerdict(status=policy, policy_version="test", tier="secure"),
    )


def test_all_three_verdicts_must_pass() -> None:
    assert _decision().is_eligible()
    assert not _decision(syntax=VerdictStatus.FAIL).is_eligible()
    assert not _decision(probe=VerdictStatus.FAIL).is_eligible()
    assert not _decision(policy=VerdictStatus.FAIL).is_eligible()


def test_expired_probe_blocks_publication() -> None:
    now = datetime.now(timezone.utc)
    decision = PublicationDecision(
        syntax=SyntaxVerdict(VerdictStatus.PASS, "test"),
        probe=ProbeVerdict(
            VerdictStatus.PASS,
            checked_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        ),
        policy=PolicyVerdict(VerdictStatus.PASS, "test", "secure"),
    )
    assert decision.probe.effective_status(now) == VerdictStatus.EXPIRED
    assert not decision.is_eligible()


def test_raw_tier_can_skip_fresh_probe_but_not_failed_probe() -> None:
    decision = _decision(probe=VerdictStatus.UNKNOWN)
    assert decision.is_eligible(require_fresh_probe=False)
    assert not _decision(probe=VerdictStatus.FAIL).is_eligible(require_fresh_probe=False)
