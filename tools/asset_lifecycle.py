from __future__ import annotations

from typing import Any

CANONICAL_LIFECYCLE_STAGES = {
    'generated_file_pending_qa',
    'file_qa_pass_pending_visual_review',
    'file_qa_warn_pending_visual_review',
    'visual_review_pending',
    'visual_rejected',
    'owner_approved_pending_promotion',
    'promoted_integrated_pending_verification',
    'promoted_integrated_verified',
    'archived_smoke',
    'superseded',
}

LEGACY_STATUS_TO_LIFECYCLE = {
    # Generated candidates.
    'pending_file_qa': 'generated_file_pending_qa',
    'qa_pass_candidate_not_promoted': 'file_qa_pass_pending_visual_review',
    'qa_pass_candidate_not_promoted_pending_owner_review': 'file_qa_pass_pending_visual_review',
    'qa_warn_candidate_not_promoted': 'file_qa_warn_pending_visual_review',
    'qa_warn_pass_candidate_not_promoted': 'file_qa_warn_pending_visual_review',
    'pending_visual_review': 'visual_review_pending',
    'pending_visual_review_not_promoted': 'visual_review_pending',
    'pending_visual_review_not_promoted_contact_overlay_created': 'visual_review_pending',
    'pending_visual_review_not_promoted_hybrid_cleanplate': 'visual_review_pending',
    'not_promoted_pending_owner_approval': 'file_qa_pass_pending_visual_review',
    'not_promoted': 'visual_review_pending',
    'not_promoted_review_candidate_only': 'visual_review_pending',
    # Rejection/hold states.
    'rejected': 'visual_rejected',
    'semantic_rejected': 'visual_rejected',
    'semantic_rejected_prompt_routing': 'visual_rejected',
    'rejected_semantic_mismatch': 'visual_rejected',
    'visual_rejected': 'visual_rejected',
    # Promotion states.
    'approved_by_owner_file_qa_pass': 'owner_approved_pending_promotion',
    'owner_approved_promoted': 'promoted_integrated_pending_verification',
    'approved_promoted': 'promoted_integrated_pending_verification',
    'owner_approved_promoted_integrated_pending_verification': 'promoted_integrated_pending_verification',
    'approved_promoted_scene_integrated_verified': 'promoted_integrated_verified',
    'qa_pass_approved_promoted_scene_replacement_verified': 'promoted_integrated_verified',
    'approved_promoted_reference_declared_verified': 'promoted_integrated_verified',
    'promoted_to_game_assets_declared_scene_replacement_verified': 'promoted_integrated_verified',
    'promoted_to_game_assets_reference': 'promoted_integrated_pending_verification',
    'promoted_to_game_assets_declared_reference': 'promoted_integrated_pending_verification',
    # Queue/archive states.
    'archived_smoke': 'archived_smoke',
    'archived': 'superseded',
    'superseded': 'superseded',
}


def normalize_token(value: Any) -> str:
    return str(value or '').strip().lower()


def is_valid_lifecycle_stage(value: Any) -> bool:
    return normalize_token(value) in CANONICAL_LIFECYCLE_STAGES


def infer_lifecycle_stage(record: dict[str, Any]) -> str:
    existing = normalize_token(record.get('lifecycle_stage'))
    if existing in CANONICAL_LIFECYCLE_STAGES:
        return existing
    for key in ('lifecycle_stage', 'queue_status', 'qa_status', 'promotion_status', 'status', 'decision'):
        raw = normalize_token(record.get(key))
        if raw in LEGACY_STATUS_TO_LIFECYCLE:
            return LEGACY_STATUS_TO_LIFECYCLE[raw]
    # If a file has already been promoted but there is no richer evidence, keep it
    # out of the candidate queue and require a later integration gate to verify it.
    if record.get('promoted_path'):
        return 'promoted_integrated_pending_verification'
    if record.get('candidate_copies') or record.get('output_paths'):
        return 'generated_file_pending_qa'
    return 'generated_file_pending_qa'


def apply_lifecycle(record: dict[str, Any], *, stage: str | None = None, preserve_legacy: bool = True) -> bool:
    resolved = normalize_token(stage) if stage else infer_lifecycle_stage(record)
    if resolved not in CANONICAL_LIFECYCLE_STAGES:
        raise ValueError(f'unknown lifecycle_stage: {stage!r}')
    changed = record.get('lifecycle_stage') != resolved
    record['lifecycle_stage'] = resolved
    metadata = record.get('metadata')
    if isinstance(metadata, dict):
        if metadata.get('lifecycle_stage') != resolved:
            metadata['lifecycle_stage'] = resolved
            changed = True
        if preserve_legacy:
            for key in ('qa_status', 'promotion_status', 'status'):
                legacy_key = f'legacy_{key}'
                if record.get(key) and not metadata.get(legacy_key):
                    metadata[legacy_key] = record.get(key)
                    changed = True
    return changed
