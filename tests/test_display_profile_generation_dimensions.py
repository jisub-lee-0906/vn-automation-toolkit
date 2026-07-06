import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import generation_dimensions, renpy_dimensions


def test_generation_dimensions_reads_primary_resolution_string():
    contract = {
        "display_profile": {
            "profile_id": "mobile_portrait_9_16_final",
            "aspect_ratio": "9:16",
            "renpy_width": 720,
            "renpy_height": 1280,
            "generation_resolution_primary": "832x1472",
        }
    }

    assert generation_dimensions(contract, fallback_width=1024, fallback_height=576) == (832, 1472)
    assert renpy_dimensions(contract) == (720, 1280)


def test_explicit_generation_width_height_override_resolution_string():
    contract = {
        "display_profile": {
            "profile_id": "mobile_portrait_9_16_final",
            "generation_resolution_primary": "832x1472",
            "generation_width": 768,
            "generation_height": 1344,
        }
    }

    assert generation_dimensions(contract, fallback_width=1024, fallback_height=576) == (768, 1344)


def test_generation_dimensions_legacy_fallback_without_profile():
    assert generation_dimensions({}, fallback_width=1024, fallback_height=576) == (1024, 576)
