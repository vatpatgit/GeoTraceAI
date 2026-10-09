import pytest

from app.geo.config import SeverityConfig
from app.geo.severity import severity_for


@pytest.mark.parametrize("area,expected", [(100, "low"), (2_500, "medium"), (9_999, "medium"), (10_000, "high"), (49_999, "high"), (50_000, "critical")])
def test_area_bands_are_the_documented_thresholds(area, expected):
    assert severity_for(area, None, None, SeverityConfig())[0] == expected


def test_magnitude_and_proximity_each_escalate_one_tier_with_reasons():
    cfg = SeverityConfig()
    tier, reasons = severity_for(3_000, 0.9, 500, cfg)  # medium -> high (magnitude) -> critical (proximity)
    assert tier == "critical" and any("magnitude" in r for r in reasons) and any("monitored boundary" in r for r in reasons)
    assert severity_for(3_000, 0.5, 5_000, cfg)[0] == "medium"  # neither condition met
    assert severity_for(60_000, 0.99, 0, cfg)[0] == "critical"  # capped, no overflow


def test_proximity_escalation_can_be_disabled_and_thresholds_are_configurable():
    cfg = SeverityConfig(escalate_on_proximity=False, area_m2_medium=10, area_m2_high=20, area_m2_critical=30)
    assert severity_for(25, None, 1, cfg)[0] == "high"
