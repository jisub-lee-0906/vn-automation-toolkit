#!/usr/bin/env python3
"""Create scene_event_cg prompt slots from compact emotion/framing intent."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scene_event_cg_policy import build_scene_event_cg_prompt_slots

DEFAULT_CHARACTER_FEATURES = ['brown_eyes', 'tareme', 'blunt_bangs', 'brown_hair', 'medium_hair', 'straight_hair']
DEFAULT_OUTFIT_DETAIL = ['red_bow', 'brown_cardigan', 'white_shirt', 'blue_skirt', 'brown_pantyhose', 'school_uniform']
DEFAULT_SCENE_CONTEXT = ['auditorium', 'spotlight']


def parse_tags(value: str | None, fallback: list[str] | None = None, *, label: str = 'tags') -> list[str]:
    if value is None:
        if fallback is None:
            raise RuntimeError(f'SCENE_EVENT_CG_{label.upper()}_REQUIRED')
        return list(fallback)
    return [part.strip() for part in value.split(',') if part.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', required=True)
    parser.add_argument('--asset-id', required=True)
    parser.add_argument('--emotion', default='neutral')
    parser.add_argument('--framing', default='default')
    parser.add_argument('--character-features', help='Comma-separated base character tags. Defaults to Unit 10 validated generic schoolgirl tags.')
    parser.add_argument('--outfit-detail', help='Comma-separated base outfit tags. Defaults to Unit 10 validated school uniform tags.')
    parser.add_argument('--scene-context', help='Comma-separated base scene tags. Defaults to auditorium, spotlight.')
    parser.add_argument('--visual-brief')
    parser.add_argument('--output', help='Optional output path. Defaults to docs/production/prompt_slots/<asset_id>.json')
    parser.add_argument('--allow-generic-fixture-defaults', action='store_true', help='Allow Unit 10 generic schoolgirl/auditorium fixture defaults. Unsafe for production unless explicitly requested.')
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    output = Path(args.output).resolve() if args.output else project_root / 'docs/production/prompt_slots' / f'{args.asset_id}.json'
    prompt_slots_root = (project_root / 'docs/production/prompt_slots').resolve()
    try:
        output.relative_to(prompt_slots_root)
    except ValueError as exc:
        raise RuntimeError(f'Output prompt slots must be under {prompt_slots_root}: {output}') from exc

    fixture_defaults = args.allow_generic_fixture_defaults
    data = build_scene_event_cg_prompt_slots(
        asset_id=args.asset_id,
        emotion=args.emotion,
        framing=args.framing,
        base_character_features=parse_tags(args.character_features, DEFAULT_CHARACTER_FEATURES if fixture_defaults else None, label='character_features'),
        base_outfit_detail=parse_tags(args.outfit_detail, DEFAULT_OUTFIT_DETAIL if fixture_defaults else None, label='outfit_detail'),
        base_scene_context=parse_tags(args.scene_context, DEFAULT_SCENE_CONTEXT if fixture_defaults else None, label='scene_context'),
        visual_brief=args.visual_brief,
    )
    data['fixture_defaults_used'] = fixture_defaults
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PROMPT_SLOTS {output}')
    print(f"ROUTE_MODE {data['scene_event_route_mode']}")
    print(f"EMOTION {data['emotion']}")
    print(f"FRAMING {data['framing']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
