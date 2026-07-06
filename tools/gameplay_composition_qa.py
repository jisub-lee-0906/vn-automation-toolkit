#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import add_project_args, build_project_paths, load_json, require_under, resolve_project_path, save_json


def rect_from_frac(spec: dict[str, Any], width: int, height: int) -> tuple[int, int, int, int]:
    def coord(key: str, limit: int) -> int:
        v = float(spec[key])
        return int(round(v * limit)) if 0 <= v <= 1 else int(round(v))
    x1 = max(0, min(width, coord('x1', width)))
    y1 = max(0, min(height, coord('y1', height)))
    x2 = max(0, min(width, coord('x2', width)))
    y2 = max(0, min(height, coord('y2', height)))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return x1, y1, x2, y2


def area(rect: tuple[int, int, int, int]) -> int:
    return max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])


def intersect(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    return max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])


def bbox_from_mask(mask_pixels: list[tuple[int, int]], fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    if not mask_pixels:
        return fallback[0], fallback[1], fallback[0], fallback[1]
    xs = [p[0] for p in mask_pixels]
    ys = [p[1] for p in mask_pixels]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def color_distance(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def detect_color_bbox(img: Image.Image, region: tuple[int, int, int, int], color: list[int], tolerance: float) -> tuple[tuple[int, int, int, int], int]:
    rgb = img.convert('RGB')
    target = (int(color[0]), int(color[1]), int(color[2]))
    x1, y1, x2, y2 = region
    points: list[tuple[int, int]] = []
    pix = rgb.load()
    if pix is None:
        return (region[0], region[1], region[0], region[1]), 0
    step = 1
    for y in range(y1, y2, step):
        for x in range(x1, x2, step):
            pixel = pix[x, y]
            if not isinstance(pixel, tuple):
                pixel = (int(pixel), int(pixel), int(pixel))
            if color_distance((int(pixel[0]), int(pixel[1]), int(pixel[2])), target) <= tolerance:
                points.append((x, y))
    return bbox_from_mask(points, region), len(points)


def region_luma(img: Image.Image, rect: tuple[int, int, int, int]) -> dict[str, float]:
    if area(rect) <= 0:
        return {'mean_luma': 0.0, 'stdev_luma': 0.0}
    crop = img.crop(rect).convert('L')
    stat = ImageStat.Stat(crop)
    return {'mean_luma': round(float(stat.mean[0]), 3), 'stdev_luma': round(float(stat.stddev[0]), 3)}


def analyze_capture(project_root: Path, capture: dict[str, Any]) -> dict[str, Any]:
    raw_screenshot = capture.get('screenshot') or capture.get('path')
    if not raw_screenshot:
        return {'name': capture.get('name', ''), 'status': 'fail', 'issues': ['missing_screenshot_path']}
    screenshot = resolve_project_path(project_root, raw_screenshot, 'screenshot').resolve()
    require_under(screenshot, project_root, 'screenshot')
    if not screenshot.exists():
        return {'name': capture.get('name', ''), 'status': 'fail', 'issues': [f'screenshot_missing:{screenshot}']}
    img = Image.open(screenshot).convert('RGB')
    width, height = img.size
    issues: list[str] = []
    if 'expected_size' in capture:
        expected_size = list(capture.get('expected_size') or [])
        if len(expected_size) == 2:
            expected_w, expected_h = int(expected_size[0]), int(expected_size[1])
            if (width, height) != (expected_w, expected_h):
                issues.append(f'unexpected_image_size actual={width}x{height} expected={expected_w}x{expected_h}')
    textbox = rect_from_frac(capture.get('textbox_region', {'x1': 0, 'y1': 0.78, 'x2': 1, 'y2': 1}), width, height)
    min_area = float(capture.get('min_character_area_ratio', 0.045))
    max_area = float(capture.get('max_character_area_ratio', 0.42))
    max_textbox_overlap = float(capture.get('max_textbox_overlap_ratio', 0.08))
    tolerance = float(capture.get('color_tolerance', 48))
    characters: list[dict[str, Any]] = []
    bboxes: list[tuple[str, tuple[int, int, int, int]]] = []
    frame_area = max(1, width * height)
    raw_characters = capture.get('characters', [])
    characters_spec = raw_characters if isinstance(raw_characters, list) else []
    min_characters = int(capture.get('min_characters', 0) or 0)
    if len(characters_spec) < min_characters:
        issues.append(f'min_characters count={len(characters_spec)} < {min_characters}')
    for char in characters_spec:
        name = str(char.get('name', 'character'))
        expected = rect_from_frac(char.get('expected_region', {'x1': 0, 'y1': 0, 'x2': 1, 'y2': 1}), width, height)
        if 'declared_bbox' in char:
            bbox = rect_from_frac(char['declared_bbox'], width, height)
            matched = None
        elif 'dominant_color' not in char:
            issues.append(f'{name}:missing_dominant_color_for_machine_check')
            bbox = expected
            matched = 0
        else:
            bbox, matched = detect_color_bbox(img, expected, list(char['dominant_color']), float(char.get('color_tolerance', tolerance)))
        bbox_area = area(bbox)
        area_ratio = bbox_area / frame_area
        overlap_ratio = area(intersect(bbox, textbox)) / max(1, bbox_area)
        clipped = bbox[0] <= 1 or bbox[1] <= 1 or bbox[2] >= width - 1 or bbox[3] >= height - 1
        char_result = {
            'name': name,
            'expected_region_px': list(expected),
            'observed_bbox_px': list(bbox),
            'matched_pixels': matched,
            'area_ratio': round(area_ratio, 6),
            'textbox_overlap_ratio': round(overlap_ratio, 6),
            'clipped_to_frame': clipped,
            **region_luma(img, bbox),
        }
        if area_ratio < min_area:
            issues.append(f'{name}:missing_or_too_small area_ratio={area_ratio:.4f} < {min_area:.4f}')
        if area_ratio > max_area:
            issues.append(f'{name}:too_large area_ratio={area_ratio:.4f} > {max_area:.4f}')
        if overlap_ratio > max_textbox_overlap:
            issues.append(f'{name}:textbox_overlap ratio={overlap_ratio:.4f} > {max_textbox_overlap:.4f}')
        if clipped:
            issues.append(f'{name}:clipped_to_frame')
        characters.append(char_result)
        bboxes.append((name, bbox))
    if len(bboxes) >= 2:
        min_gap = float(capture.get('min_inter_character_gap_ratio', 0.0))
        max_overlap = float(capture.get('max_inter_character_overlap_ratio', 0.12))
        for i in range(len(bboxes)):
            for j in range(i + 1, len(bboxes)):
                name_a, a = bboxes[i]
                name_b, b = bboxes[j]
                inter_area = area(intersect(a, b))
                smaller = max(1, min(area(a), area(b)))
                overlap = inter_area / smaller
                horizontal_gap_px = max(0, max(a[0], b[0]) - min(a[2], b[2]))
                gap_ratio = horizontal_gap_px / max(1, width)
                if overlap > max_overlap:
                    issues.append(f'{name_a}/{name_b}:inter_character_overlap ratio={overlap:.4f} > {max_overlap:.4f}')
                if inter_area == 0 and gap_ratio < min_gap:
                    issues.append(f'{name_a}/{name_b}:inter_character_gap ratio={gap_ratio:.4f} < {min_gap:.4f}')
    bg_region = rect_from_frac(capture.get('background_sample_region', {'x1': 0.05, 'y1': 0.08, 'x2': 0.95, 'y2': 0.70}), width, height)
    bg_luma = region_luma(img, bg_region)
    if bg_luma['mean_luma'] < float(capture.get('min_background_mean_luma', 8)):
        issues.append(f'background_too_dark mean_luma={bg_luma["mean_luma"]}')
    if bg_luma['stdev_luma'] < float(capture.get('min_background_stdev_luma', 6)):
        issues.append(f'background_low_detail stdev_luma={bg_luma["stdev_luma"]}')
    status = 'pass' if not issues else 'fail'
    return {
        'name': capture.get('name', screenshot.stem),
        'status': status,
        'screenshot': str(screenshot),
        'image_size': [width, height],
        'textbox_region_px': list(textbox),
        'background_sample_region_px': list(bg_region),
        'background_luma': bg_luma,
        'characters': characters,
        'issues': issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate VN gameplay screenshot composition: sprite placement/scale/textbox overlap/basic background harmony.')
    add_project_args(parser)
    parser.add_argument('--plan', required=True, help='Composition QA plan JSON under project root.')
    parser.add_argument('--out', required=True, help='Output JSON under project root.')
    args = parser.parse_args()
    paths = build_project_paths(args.project_root, args.contract)
    project_root = paths.project_root
    plan_path = resolve_project_path(project_root, args.plan, 'plan').resolve()
    require_under(plan_path, project_root, 'plan')
    plan = load_json(plan_path)
    captures = [analyze_capture(project_root, item) for item in plan.get('captures', [])]
    if not captures:
        captures = [{'name': '', 'status': 'fail', 'issues': ['no_captures_in_plan']}]
    status = 'pass' if all(c.get('status') == 'pass' for c in captures) else 'fail'
    result = {
        'status': status,
        'scene_id': plan.get('scene_id'),
        'qa_type': 'gameplay_composition',
        'captures': captures,
        'policy_note': 'Machine gate for gross composition failures only; final art direction can still require visual/owner review for identity-critical assets.',
    }
    out = resolve_project_path(project_root, args.out, 'out').resolve()
    require_under(out, project_root, 'out')
    save_json(out, result)
    print('GAMEPLAY_COMPOSITION_QA')
    print('status', status)
    print('captures', len(captures))
    for capture in captures:
        print('capture', capture.get('name'), capture.get('status'))
        for issue in capture.get('issues', []):
            print('issue', issue)
    return 0 if status == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
