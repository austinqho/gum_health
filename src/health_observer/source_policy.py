"""System-wide source and privacy policy.

Every provider's collection surface should be declared here so reviewers can
audit enabled, optional, and intentionally skipped sources in one place.
"""
from __future__ import annotations

DEFAULT_ENABLED_SOURCES = {
    "apple_health.steps",
    "oura.daily_activity",
    "oura.daily_readiness",
    "oura.daily_sleep",
    "oura.sleep",
    "oura.daily_spo2",
    "oura.daily_stress",
    "oura.workout",
}

OPTIONAL_SOURCES = {
    "oura.heartrate": "high-volume time series",
    "oura.session": "guided/unguided session context",
    "oura.tag": "user-entered text; sensitive by default",
    "oura.enhanced_tag": "user-entered text; sensitive by default",
    "oura.daily_resilience": "sensitive recovery/resilience data",
    "oura.daily_cardiovascular_age": "sensitive cardiovascular estimate",
    "oura.vo2_max": "sensitive fitness estimate",
}

SKIPPED_SOURCES = {
    "oura.personal_info": "profile data such as age, sex, height, weight, and email",
    "oura.ring_battery_level": "device diagnostic data, not user context",
    "oura.ring_configuration": "device configuration data, not user context",
    "oura.rest_mode_period": "rest-mode state; not enabled until product semantics are clear",
    "oura.sleep_time": "recommendation/status data rather than raw observation",
}
