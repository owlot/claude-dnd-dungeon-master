"""Shared campaign path helpers (combat_status.py, checkpoint.py).

Canonical combat state file: campaigns/<campaign>/party/combat_state.json
(the location the combat-tracker agent documents). The campaign root
campaigns/<campaign>/combat_state.json is only a legacy fallback when the
party one does not exist.

Override for testing: set COMBAT_STATE_FILE to an absolute file path.
"""
import os

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "campaigns")


def campaign_dir(campaign: str) -> str:
    return os.path.join(BASE, campaign)


def combat_state_path(campaign: str) -> str:
    override = os.environ.get("COMBAT_STATE_FILE")
    if override:
        return override
    canonical = os.path.join(campaign_dir(campaign), "party", "combat_state.json")
    legacy = os.path.join(campaign_dir(campaign), "combat_state.json")
    if not os.path.exists(canonical) and os.path.exists(legacy):
        return legacy
    return canonical


def encounter_file(campaign: str, encounter: str) -> str:
    """info/encounters/<slug>.md (canonical); legacy encounters/<slug>.md as fallback."""
    canonical = os.path.join(campaign_dir(campaign), "info", "encounters", f"{encounter}.md")
    legacy = os.path.join(campaign_dir(campaign), "encounters", f"{encounter}.md")
    if not os.path.exists(canonical) and os.path.exists(legacy):
        return legacy
    return canonical
