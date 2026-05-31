from __future__ import annotations

import json
from pathlib import Path

from test_director_remaining_ux import create_opening_scene, seed_candidate
from test_director_ux_console import bootstrap_moonlit_library, run_cli


def prepare_pending_candidate(tmp_path: Path):
    project, _vault = bootstrap_moonlit_library(tmp_path)
    create_opening_scene(project)
    metadata_path = seed_candidate(project)
    review = run_cli('director', 'telegram-review', '--project-root', str(project))
    assert review.returncode == 0, review.stdout + review.stderr
    registry_path = project / 'docs/production/telegram_approval_registry.json'
    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    assert registry['items']
    return project, metadata_path, registry_path, registry['items'][0]


def test_telegram_review_creates_tokened_registry_and_card(tmp_path: Path):
    project, metadata_path, registry_path, item = prepare_pending_candidate(tmp_path)

    card = project / 'docs/production/director_cards/telegram_asset_review.md'
    assert registry_path.exists()
    assert card.exists()
    assert item['status'] == 'pending_telegram_approval'
    assert item['metadata_path'] == str(metadata_path)
    assert item['approval_phrase'] == f"승인 {item['token']}"
    text = card.read_text(encoding='utf-8')
    assert item['token'] in text
    assert 'vn-auto director telegram-approve' in text
    assert 'MEDIA:' in text


def test_telegram_approve_rejects_unknown_or_wrong_token_phrase(tmp_path: Path):
    project, _metadata_path, _registry_path, item = prepare_pending_candidate(tmp_path)

    unknown = run_cli(
        'director', 'telegram-approve',
        '--project-root', str(project),
        '--token', 'VN-UNKNOWN',
        '--approved-text', '승인 VN-UNKNOWN',
        '--approved',
    )
    assert unknown.returncode == 2
    assert 'unknown token' in unknown.stdout

    wrong_phrase = run_cli(
        'director', 'telegram-approve',
        '--project-root', str(project),
        '--token', item['token'],
        '--approved-text', '승인',
        '--approved',
    )
    assert wrong_phrase.returncode == 2
    assert 'approval text does not match token phrase' in wrong_phrase.stdout


def test_telegram_approve_consumes_token_promotes_and_rejects_reuse(tmp_path: Path):
    project, _metadata_path, registry_path, item = prepare_pending_candidate(tmp_path)

    approved = run_cli(
        'director', 'telegram-approve',
        '--project-root', str(project),
        '--token', item['token'],
        '--approved-text', item['approval_phrase'],
        '--message-id', '1396',
        '--approved',
    )
    assert approved.returncode == 0, approved.stdout + approved.stderr
    assert 'Telegram Approval Consumed' in approved.stdout
    assert 'Candidate Approved And Promoted' in approved.stdout

    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    saved = next(entry for entry in registry['items'] if entry['token'] == item['token'])
    assert saved['status'] == 'owner_approved_promoted'
    assert saved['telegram_approval_message_id'] == '1396'

    manifest = json.loads((project / 'game/data/asset_manifest.json').read_text(encoding='utf-8'))
    promoted = next(asset for asset in manifest['assets'] if asset['asset_id'] == item['asset_id'])
    assert promoted['qa_status'] == 'owner_approved_promoted'
    assert (project / 'game' / promoted['promoted_path']).exists()

    reuse = run_cli(
        'director', 'telegram-approve',
        '--project-root', str(project),
        '--token', item['token'],
        '--approved-text', item['approval_phrase'],
        '--approved',
    )
    assert reuse.returncode == 2
    assert 'token is not pending' in reuse.stdout


def test_telegram_message_binding_allows_plain_reply_approval(tmp_path: Path):
    project, _metadata_path, registry_path, item = prepare_pending_candidate(tmp_path)

    bind = run_cli(
        'director', 'telegram-bind-message',
        '--project-root', str(project),
        '--token', item['token'],
        '--message-id', '2001',
        '--chat-id', '8757392807',
    )
    assert bind.returncode == 0, bind.stdout + bind.stderr
    assert 'Telegram Review Message Bound' in bind.stdout

    approved = run_cli(
        'director', 'telegram-approve-message',
        '--project-root', str(project),
        '--reply-to-message-id', '2001',
        '--approved-text', '승인',
        '--approval-message-id', '2002',
        '--approved',
    )
    assert approved.returncode == 0, approved.stdout + approved.stderr
    assert 'Telegram Approval Consumed' in approved.stdout
    assert 'Candidate Approved And Promoted' in approved.stdout

    registry = json.loads(registry_path.read_text(encoding='utf-8'))
    saved = next(entry for entry in registry['items'] if entry['token'] == item['token'])
    assert saved['status'] == 'owner_approved_promoted'
    assert saved['telegram_review_message_id'] == '2001'
    assert saved['telegram_reply_to_message_id'] == '2001'
    assert saved['telegram_approval_message_id'] == '2002'


def test_telegram_message_approval_rejects_unbound_reply_or_non_approval_text(tmp_path: Path):
    project, _metadata_path, _registry_path, item = prepare_pending_candidate(tmp_path)

    unbound = run_cli(
        'director', 'telegram-approve-message',
        '--project-root', str(project),
        '--reply-to-message-id', '9999',
        '--approved-text', '승인',
        '--approved',
    )
    assert unbound.returncode == 2
    assert 'no pending token bound' in unbound.stdout

    bind = run_cli(
        'director', 'telegram-bind-message',
        '--project-root', str(project),
        '--token', item['token'],
        '--message-id', '2001',
    )
    assert bind.returncode == 0, bind.stdout + bind.stderr

    wrong_text = run_cli(
        'director', 'telegram-approve-message',
        '--project-root', str(project),
        '--reply-to-message-id', '2001',
        '--approved-text', '다시 뽑아줘',
        '--approved',
    )
    assert wrong_text.returncode == 2
    assert 'neither a plain approval nor the exact token phrase' in wrong_text.stdout
