#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import add_project_args, build_project_paths, resolve_project_path, require_under, save_json


def load_scene_note(paths: Any, scene_id: str) -> str:
    obs = paths.contract.get('obsidian_project_root')
    if not obs:
        return ''
    root = Path(obs)
    for p in [root / 'Scenes' / f'{scene_id}.md', root / 'Scenes' / f'{scene_id.replace("scene_", "scene ")}.md']:
        if p.exists():
            return p.read_text(encoding='utf-8')[:4000]
    return ''


def build_story_plan(scene_id: str, note: str) -> dict[str, Any]:
    lower = note.lower()
    investigation = 'clue' in lower or 'investigation' in lower or '단서' in note or '조사' in note
    scene_function = 'first investigation clue branching' if investigation or '003' in scene_id else 'scene progression with emotional and route payoff'
    return {
        'scene_id': scene_id,
        'qa_type': 'story_plan',
        'scene_function': scene_function,
        'player_emotion_target': ['tension', 'deduction reward', 'survival agency'],
        'character_state_in': {
            'serena': 'under suspicion, using record fractures and reputation as survival tools',
            'lucian': 'armed watcher, suspicious but forced to evaluate Serena logic',
        },
        'character_state_out': {
            'serena': 'has a concrete clue or trap direction',
            'lucian': 'suspicion remains, but cooperation pressure increases',
        },
        'must_include': ['scene-specific clue or pressure turn', 'Serena agency', 'Lucian suspicion', 'record/original-text fracture'],
        'must_not_include': ['system UI revival', 'meta mechanics explanation', 'unsupported canon rewrite'],
        'beats': [
            {'beat_id': f'{scene_id}_beat_01', 'summary': 'establish the scene-specific pressure and visible investigation target', 'player_reward': 'clear objective'},
            {'beat_id': f'{scene_id}_beat_02', 'summary': 'Serena reframes an apparent weakness as leverage', 'player_reward': 'deduction/agency payoff'},
            {'beat_id': f'{scene_id}_beat_03', 'summary': 'Lucian challenges the logic, creating relationship friction and route pressure', 'player_reward': 'character tension'},
            {'beat_id': f'{scene_id}_beat_04', 'summary': 'end on a concrete clue, trap, or next-scene hook', 'player_reward': 'forward momentum'},
        ],
        'choice_candidates': [
            {'choice_text': '증거로 삼는다', 'player_intent': 'deductive pressure', 'state_delta': {'culprit_pressure': 1}},
            {'choice_text': '미끼로 쓴다', 'player_intent': 'villainess trap', 'state_delta': {'lucian_suspicion': 1, 'culprit_pressure': 1}},
            {'choice_text': '일부러 숨긴다', 'player_intent': 'information control', 'state_delta': {'serena_leverage': 1}},
        ],
        'asset_opportunities': [
            {'asset_type': 'background', 'role': 'scene-specific location identity', 'count_hint': 3, 'promotion': 'delegated_auto_possible'},
            {'asset_type': 'bgm', 'role': 'quiet investigation loop plus pressure variant', 'count_hint': 2, 'promotion': 'delegated_auto_possible'},
            {'asset_type': 'sfx', 'role': 'clue reveal / paper / seal / step stinger', 'count_hint': 3, 'promotion': 'delegated_auto_possible'},
            {'asset_type': 'prop_cg', 'role': 'readable visual reward for the concrete clue', 'count_hint': 3, 'promotion': 'human_review_required'},
            {'asset_type': 'event_cg', 'role': 'cinematic clue or confrontation beat', 'count_hint': 2, 'promotion': 'human_gated'},
            {'asset_type': 'char_expression', 'role': 'Serena/Lucian reaction variation', 'count_hint': 2, 'promotion': 'human_gated'},
        ],
        'story_qa_targets': {
            'canon_fit': 5,
            'character_voice': 4,
            'emotional_progression': 4,
            'player_reward': 4,
            'route_value': 4,
            'foreshadowing': 4,
            'repetition_risk': 2,
        },
        'source_context_excerpt': note[:1000],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Create a structured VN scene story plan with asset opportunities.')
    add_project_args(parser)
    parser.add_argument('--scene-id', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    paths = build_project_paths(args.project_root, args.contract)
    out = resolve_project_path(paths.project_root, args.out, 'out').resolve()
    require_under(out, paths.project_root, 'out')
    plan = build_story_plan(args.scene_id, load_scene_note(paths, args.scene_id))
    save_json(out, plan)
    print('SCENE_STORY_PLAN')
    print('scene_id', args.scene_id)
    print('asset_opportunities', len(plan['asset_opportunities']))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
