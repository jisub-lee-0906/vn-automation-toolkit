from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/run_scene_background_smoke.py'


def load_runner():
    spec = importlib.util.spec_from_file_location('run_scene_background_smoke', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_hidden_scene_background_routing_is_removed():
    runner = load_runner()

    assert not hasattr(runner, 'choose_background_tags')


def test_load_agent_authored_background_prompt_slots(tmp_path: Path):
    runner = load_runner()
    path = tmp_path / 'slots.json'
    path.write_text(json.dumps({
        'workflow_id': 'scene_background',
        'asset_id': 'bg_bus_interior_dawn',
        'prompt_slots': {
            'background_theme': ['bus_interior', 'vehicle_interior', 'bus', 'chair', 'window', 'rain', 'wet', 'reflection'],
            'time_mood': ['indoors', 'dawn'],
            'negative_tags': ['train_interior'],
            'negative_rationale': {'train_interior': 'avoid rail-transit misread'},
        },
        'visual_brief': 'Dawn city bus interior with no people.',
        'tag_rationale': {
            'bus_interior': 'primary semantic anchor',
            'chair': 'broad supporting cue only',
        },
    }), encoding='utf-8')

    theme, mood, negative_tags, data = runner.load_prompt_slots(path, 'scene_background', 'bg_bus_interior_dawn')

    assert 'bus_interior' in theme
    assert 'classroom' not in theme
    assert mood == ['indoors', 'dawn']
    assert negative_tags == ['train_interior']
    assert data['asset_id'] == 'bg_bus_interior_dawn'
    notes = runner.prompt_context_notes(data)
    assert notes['visual_brief'] == 'Dawn city bus interior with no people.'
    assert notes['tag_rationale']['bus_interior'] == 'primary semantic anchor'
    assert notes['negative_rationale']['train_interior'] == 'avoid rail-transit misread'
