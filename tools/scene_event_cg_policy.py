#!/usr/bin/env python3
"""Scene event CG emotion/framing policy resolver.

This module converts a compact production intent such as
`emotion=sad, framing=default` into the route mode and tag extras discovered
through Unit 10L/10M validation. It is intentionally pure and dependency-light
so runners/tests can reuse the policy without triggering ComfyUI.
"""
from __future__ import annotations

from copy import deepcopy

EMOTION_POLICIES = {
    'neutral': {
        'character_features_extra': ['expressionless', 'closed_mouth'],
        'default_route': 'production_character',
    },
    'happy': {
        'character_features_extra': ['smile', 'open_mouth'],
        'default_route': 'production_character_front',
    },
    'serious': {
        'character_features_extra': ['serious', 'closed_mouth'],
        'default_route': 'production_character_front',
    },
    'surprised': {
        'character_features_extra': ['surprised', 'open_mouth'],
        'default_route': 'production_character_front',
    },
    'sad': {
        'character_features_extra': ['sad', 'tears', 'frown', 'closed_mouth'],
        'default_route': 'production_character_front',
    },
}

FRAMING_POLICIES = {
    'default': {
        'route_by_emotion_default': True,
        'scene_context_extra_by_route': {
            'production_character': ['upper_body', 'looking_at_viewer'],
            'production_character_front': ['upper_body', 'looking_at_viewer', 'facing_viewer', 'straight_on'],
        },
    },
    'upper': {
        'scene_event_route_mode': 'production_character',
        'scene_context_extra': ['upper_body', 'looking_at_viewer'],
    },
    'front': {
        'scene_event_route_mode': 'production_character_front',
        'scene_context_extra': ['upper_body', 'looking_at_viewer', 'facing_viewer', 'straight_on'],
    },
    'cutin': {
        'scene_event_route_mode': 'cut_in',
        'scene_context_extra': ['portrait', 'close-up', 'headshot', 'solo_focus'],
    },
    'cowboy': {
        'scene_event_route_mode': 'production_character_cowboy',
        'scene_context_extra': ['cowboy_shot', 'looking_at_viewer'],
    },
    'two_shot': {
        'scene_event_route_mode': 'production_character_front',
        'scene_context_extra': ['1girl', '1boy', 'upper_body', 'facing_another'],
        'review_gate': 'multi_character_reference_required',
        'executable': False,
    },
    'over_the_shoulder': {
        'scene_event_route_mode': 'production_character_front',
        'scene_context_extra': ['1girl', '1boy', 'upper_body', 'from_behind', 'facing_another'],
        'review_gate': 'multi_character_reference_required',
        'executable': False,
    },
}

INTERACTION_POLICIES = {
    'none': [],
    'confrontation': ['confrontation'],
    'conversation': ['facing_another'],
    'distance': ['standing'],
    'hand_reach': ['reaching_towards_another'],
}


def unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        token = str(value).strip()
        if not token or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def resolve_scene_event_cg_policy(
    *,
    emotion: str = 'neutral',
    framing: str = 'default',
    subject_count: int = 1,
    interaction: str = 'none',
) -> dict:
    emotion_key = str(emotion or 'neutral').strip().lower().replace('-', '_')
    framing_key = str(framing or 'default').strip().lower().replace('-', '_')
    interaction_key = str(interaction or 'none').strip().lower().replace('-', '_')
    if emotion_key not in EMOTION_POLICIES:
        raise RuntimeError(
            'UNKNOWN_SCENE_EVENT_EMOTION: '
            + emotion_key
            + '; expected one of '
            + ', '.join(sorted(EMOTION_POLICIES))
        )
    if framing_key not in FRAMING_POLICIES:
        raise RuntimeError(
            'UNKNOWN_SCENE_EVENT_FRAMING: '
            + framing_key
            + '; expected one of '
            + ', '.join(sorted(FRAMING_POLICIES))
        )
    if interaction_key not in INTERACTION_POLICIES:
        raise RuntimeError(
            'UNKNOWN_SCENE_EVENT_INTERACTION: '
            + interaction_key
            + '; expected one of '
            + ', '.join(sorted(INTERACTION_POLICIES))
        )
    if int(subject_count or 1) < 1:
        raise RuntimeError('SCENE_EVENT_SUBJECT_COUNT_MUST_BE_POSITIVE')

    emotion_policy = deepcopy(EMOTION_POLICIES[emotion_key])
    framing_policy = deepcopy(FRAMING_POLICIES[framing_key])
    if framing_policy.get('route_by_emotion_default'):
        route = emotion_policy['default_route']
        scene_extra = framing_policy['scene_context_extra_by_route'][route]
    else:
        route = framing_policy['scene_event_route_mode']
        scene_extra = framing_policy['scene_context_extra']
    scene_extra = unique_preserve_order(scene_extra + INTERACTION_POLICIES[interaction_key])
    review_gate = framing_policy.get('review_gate')
    executable = framing_policy.get('executable', True)
    if int(subject_count or 1) > 1 and not review_gate:
        review_gate = 'multi_character_reference_required'
        executable = False
        scene_extra = unique_preserve_order(['1girl', '1boy'] + scene_extra)

    return {
        'emotion': emotion_key,
        'framing': framing_key,
        'subject_count': int(subject_count or 1),
        'interaction': interaction_key,
        'scene_event_route_mode': route,
        'character_features_extra': emotion_policy['character_features_extra'],
        'scene_context_extra': scene_extra,
        'review_gate': review_gate,
        'executable': executable,
    }


def build_reference_conditioning_request(
    *,
    mode: str = 'none',
    reference_assets: list[str] | None = None,
    reason: str | None = None,
) -> dict:
    mode_key = str(mode or 'none').strip().lower().replace('-', '_')
    assets = unique_preserve_order(reference_assets or [])
    if mode_key == 'none':
        return {
            'mode': 'none',
            'status': 'not_requested',
            'reference_assets': [],
            'approval_required': False,
            'reason': reason or '',
        }
    if mode_key not in {'identity_reference', 'composition_reference', 'identity_and_composition_reference'}:
        raise RuntimeError('UNKNOWN_REFERENCE_CONDITIONING_MODE: ' + mode_key)
    if not assets:
        raise RuntimeError('REFERENCE_CONDITIONING_ASSETS_REQUIRED')
    return {
        'mode': mode_key,
        'status': 'preflight_required_not_executable_by_default',
        'reference_assets': assets,
        'approval_required': True,
        'reason': reason or 'reference conditioning requested for review-only preflight',
        'safety_note': 'This schema records intent only; no reference-conditioning workflow is executed unless a validated workflow and explicit owner approval exist.',
    }


def build_scene_event_cg_prompt_slots(
    *,
    asset_id: str,
    emotion: str = 'neutral',
    framing: str = 'default',
    subject_count: int = 1,
    interaction: str = 'none',
    subjects: list[str] | None = None,
    reference_conditioning: dict | None = None,
    base_character_features: list[str] | None = None,
    base_outfit_detail: list[str] | None = None,
    base_scene_context: list[str] | None = None,
    visual_brief: str | None = None,
) -> dict:
    resolved = resolve_scene_event_cg_policy(
        emotion=emotion,
        framing=framing,
        subject_count=subject_count,
        interaction=interaction,
    )
    character_features = unique_preserve_order((base_character_features or []) + resolved['character_features_extra'])
    outfit_detail = unique_preserve_order(base_outfit_detail or [])
    scene_context = unique_preserve_order((base_scene_context or []) + resolved['scene_context_extra'])
    if not asset_id:
        raise RuntimeError('SCENE_EVENT_POLICY_ASSET_ID_REQUIRED')
    if not character_features:
        raise RuntimeError('SCENE_EVENT_POLICY_CHARACTER_FEATURES_REQUIRED')
    if not outfit_detail:
        raise RuntimeError('SCENE_EVENT_POLICY_OUTFIT_DETAIL_REQUIRED')
    if not scene_context:
        raise RuntimeError('SCENE_EVENT_POLICY_SCENE_CONTEXT_REQUIRED')
    ref_request = reference_conditioning or build_reference_conditioning_request(mode='none')
    return {
        'workflow_id': 'scene_event_cg',
        'asset_id': asset_id,
        'asset_type': 'event_cg',
        'scene_event_route_mode': resolved['scene_event_route_mode'],
        'emotion': resolved['emotion'],
        'framing': resolved['framing'],
        'subject_count': resolved['subject_count'],
        'subjects': unique_preserve_order(subjects or []),
        'interaction': resolved['interaction'],
        'review_gate': resolved.get('review_gate'),
        'executable': resolved.get('executable', True),
        'reference_conditioning': ref_request,
        'visual_brief': visual_brief or f"scene_event_cg {resolved['emotion']} {resolved['framing']} generated from policy resolver",
        'prompt_slots': {
            'character_features': character_features,
            'outfit_detail': outfit_detail,
            'scene_context': scene_context,
        },
    }
