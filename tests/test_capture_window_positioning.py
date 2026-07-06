
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'


def load_module():
    spec = importlib.util.spec_from_file_location('capture_scene_under_test', TOOLS / 'capture_scene_contact_sheet.py')
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_window_adjustment_preserves_rect_by_default():
    mod = load_module()
    rect = (100, 200, 530, 964)
    plan = mod.window_adjustment_plan(rect, target_window_size=(430, 764), preserve_window_rect=True, restore_window_rect=True)
    assert plan['move_before_capture'] is False
    assert plan['capture_rect'] == list(rect)
    assert plan['restore_after_capture'] is False


def test_window_adjustment_can_force_size_and_restore_original_rect():
    mod = load_module()
    rect = (100, 200, 530, 964)
    plan = mod.window_adjustment_plan(
        rect,
        target_window_size=(430, 764),
        preserve_window_rect=False,
        restore_window_rect=True,
        force_position=(80, 40),
    )
    assert plan['move_before_capture'] is True
    assert plan['target_rect'] == [80, 40, 510, 804]
    assert plan['restore_after_capture'] is True
    assert plan['restore_rect'] == list(rect)
