import importlib.util
import itertools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / 'tools/scene_event_cg_policy.py'
TOOLS = ROOT / 'tools'
WORKFLOW_ROOT = Path('E:/workspace/comfyui-game-asset-workflows')


def load_policy():
    spec = importlib.util.spec_from_file_location('scene_event_cg_policy', POLICY)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_scene_event_policy_output_tags_validate_against_danbooru_taxonomy():
    sys.path.insert(0, str(TOOLS))
    from danbooru_taxonomy import validate_tags

    policy = load_policy()
    tags = set()
    for emotion, framing in itertools.product(policy.EMOTION_POLICIES, policy.FRAMING_POLICIES):
        for interaction in policy.INTERACTION_POLICIES:
            resolved = policy.resolve_scene_event_cg_policy(
                emotion=emotion,
                framing=framing,
                subject_count=2 if framing in {'two_shot', 'over_the_shoulder'} else 1,
                interaction=interaction,
            )
            tags.update(resolved['character_features_extra'])
            tags.update(resolved['scene_context_extra'])
    result, meta = validate_tags(WORKFLOW_ROOT, sorted(tags))
    assert sorted(result) == sorted(tags)
    assert meta['taxonomy_source'] == 'db'
