from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
SCRIPT = TOOLS / 'run_char_base_smoke.py'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))


def load_runner():
    spec = importlib.util.spec_from_file_location('run_char_base_smoke', SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_char_base_prompt_slots_support_optional_body_shape_and_negative_tags(tmp_path: Path):
    runner = load_runner()
    slots = {
        'workflow_id': 'char_base',
        'asset_id': 'char_test',
        'prompt_slots': {
            'character_features': ['medium_hair', 'brown_hair', 'brown_eyes'],
            'body_shape': ['small_breasts'],
            'outfit_detail': ['school_uniform', 'white_shirt', 'red_necktie'],
            'negative_tags': ['badge', 'emblem', 'bow', 'ribbon'],
        },
    }
    path = tmp_path / 'slots.json'
    path.write_text(json.dumps(slots), encoding='utf-8')

    features, outfit, body, negative, data = runner.load_prompt_slots(path, 'char_base', 'char_test')
    assert features == ['medium_hair', 'brown_hair', 'brown_eyes']
    assert body == ['small_breasts']
    assert outfit == ['school_uniform', 'white_shirt', 'red_necktie']
    assert negative == ['badge', 'emblem', 'bow', 'ribbon']
    assert data['asset_id'] == 'char_test'

    positive = runner.README_POSITIVE.format(
        body_shape_segment=', '.join(body) + ', ',
        character_features=', '.join(features),
        outfit_detail=', '.join(outfit),
    )
    assert 'small_breasts' in positive
    assert 'medium_breasts' not in positive
    assert 'red_necktie' in positive


def test_char_base_default_wrapper_has_no_forced_body_size():
    runner = load_runner()
    assert 'medium_breasts' not in runner.README_POSITIVE
    positive = runner.README_POSITIVE.format(
        body_shape_segment='',
        character_features='medium_hair, brown_hair, brown_eyes',
        outfit_detail='school_uniform, white_shirt',
    )
    assert '1girl, solo, cowboy_shot' in positive
    assert 'medium_breasts' not in positive
