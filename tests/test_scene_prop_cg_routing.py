from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/run_scene_prop_cg_smoke.py'


def load_runner():
    spec = importlib.util.spec_from_file_location('run_scene_prop_cg_smoke', SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_load_agent_authored_prop_prompt_slots_with_semantic_segment(tmp_path: Path):
    runner = load_runner()
    path = tmp_path / 'slots.json'
    path.write_text(json.dumps({
        'workflow_id': 'scene_prop_cg',
        'asset_id': 'prop_red_contract',
        'prompt_slots': {
            'item_form': ['letter', 'blank_page'],
            'material_detail': ['paper', 'glowing'],
            'placement_background': ['wooden_table', 'shadow'],
            'semantic_prompt': 'red magical contract document, sealed noble pact clue',
            'style_prompt': 'dark red wax seal, ominous fantasy evidence, not a love letter',
            'extra_negative_prompt': 'envelope, handwriting, extra objects',
        },
        'visual_brief': 'Red magical contract prop on a wooden desk.',
    }), encoding='utf-8')

    item_form, material, placement, data = runner.load_prompt_slots(path, 'scene_prop_cg', 'prop_red_contract')

    assert item_form == ['letter', 'blank_page']
    assert material == ['paper', 'glowing']
    assert placement == ['wooden_table', 'shadow']
    assert runner.prompt_context_notes(data)['visual_brief'] == 'Red magical contract prop on a wooden desk.'
    assert runner.semantic_prompt_segment(data) == 'red magical contract document, sealed noble pact clue, dark red wax seal, ominous fantasy evidence, not a love letter'
    assert runner.extra_negative_prompt_segment(data) == 'envelope, handwriting, extra objects'
    positive, shape = runner.build_positive_prompt(item_form, material, placement, data, runner.semantic_prompt_segment(data))
    assert shape == 'quality_first_wrapper'
    assert positive.startswith('masterpiece, best_quality')
    assert 'red magical contract document' in positive


def test_prop_prompt_shape_screen_device_black_screen_safe(tmp_path: Path):
    runner = load_runner()
    path = tmp_path / 'phone_slots.json'
    path.write_text(json.dumps({
        'workflow_id': 'scene_prop_cg',
        'asset_id': 'prop_phone',
        'prompt_slots': {
            'item_form': ['smartphone', 'phone'],
            'material_detail': ['shadow'],
            'placement_background': ['wooden_table'],
            'prompt_shape': 'screen_device_black_screen_safe',
            'semantic_prompt': 'small plain smartphone on wooden tabletop, featureless empty black glass front, display powered off, completely blank dark reflective glass surface, single smartphone only',
            'extra_negative_prompt': 'monitor, television, computer monitor, large display, background screen, active screen, app screen',
        },
    }), encoding='utf-8')
    item_form, material, placement, data = runner.load_prompt_slots(path, 'scene_prop_cg', 'prop_phone')
    positive, shape = runner.build_positive_prompt(item_form, material, placement, data, runner.semantic_prompt_segment(data))
    assert shape == 'screen_device_black_screen_safe'
    assert positive.startswith('small plain smartphone')
    assert 'masterpiece' in positive and positive.rfind('masterpiece') > positive.find('smartphone')
    assert 'no logo, no icons, no app UI, no text, no corner marks, no colored marks' in positive
