from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_tool(name: str):
    path = ROOT / 'tools' / f'{name}.py'
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_check_renpy_asset_refs_extracts_audio_path_from_play_sound_line():
    tool = load_tool('check_renpy_asset_refs')
    refs = tool.asset_refs_from_line('    play sound "audio/sfx/sfx_door_knock_soft.flac"')
    assert refs == ['audio/sfx/sfx_door_knock_soft.flac']


def test_check_renpy_asset_refs_ignores_dynamic_gui_template_paths():
    tool = load_tool('check_renpy_asset_refs')
    refs = tool.asset_refs_from_line('        idle "gui/scrollbar/horizontal_[prefix_]bar.png"')
    assert refs == []


def test_report_renpy_integration_gaps_extracts_audio_path_from_play_sound_line():
    tool = load_tool('report_renpy_integration_gaps')
    refs = tool.asset_refs_from_line('    play sound "audio/sfx/sfx_door_knock_soft.flac"')
    assert refs == ['audio/sfx/sfx_door_knock_soft.flac']


def test_report_renpy_integration_gaps_ignores_dynamic_gui_template_paths():
    tool = load_tool('report_renpy_integration_gaps')
    refs = tool.asset_refs_from_line('        idle "gui/scrollbar/horizontal_[prefix_]bar.png"')
    assert refs == []
