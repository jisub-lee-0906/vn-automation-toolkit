#!/usr/bin/env python3
"""Create full-image and face-crop contact sheets for event CG batch summaries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageStat


def load_batch(batch_summary: Path) -> dict:
    return json.loads(batch_summary.read_text(encoding='utf-8'))


def load_items(batch_summary: Path) -> list[dict]:
    data = load_batch(batch_summary)
    items = data.get('items') or []
    usable = []
    for item in items:
        candidate = item.get('candidate')
        if candidate and Path(candidate).exists():
            usable.append(item)
    if not usable:
        raise RuntimeError(f'No usable candidate images in batch summary: {batch_summary}')
    return usable


def fit_image(path: Path, size: tuple[int, int]) -> Image.Image:
    img = Image.open(path).convert('RGB')
    img.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', size, (238, 238, 238))
    canvas.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
    return canvas


def face_crop(path: Path, size: tuple[int, int]) -> Image.Image:
    img = Image.open(path).convert('RGB')
    crop_w = min(img.width, int(img.width * 0.42))
    crop_h = min(img.height, int(img.height * 0.72))
    cx = img.width // 2
    cy = int(img.height * 0.40)
    left = max(0, min(img.width - crop_w, cx - crop_w // 2))
    top = max(0, min(img.height - crop_h, cy - crop_h // 2))
    crop = img.crop((left, top, left + crop_w, top + crop_h))
    crop.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new('RGB', size, (238, 238, 238))
    canvas.paste(crop, ((size[0] - crop.width) // 2, (size[1] - crop.height) // 2))
    return canvas


def label_for(item: dict) -> str:
    pieces = []
    if item.get('emotion'):
        pieces.append(str(item['emotion']))
    if item.get('framing'):
        pieces.append(str(item['framing']))
    if item.get('seed') is not None:
        pieces.append('s' + str(item['seed']))
    if not pieces and item.get('asset_id'):
        pieces.append(str(item['asset_id']))
    return ' '.join(pieces)[:46]


def aspect_profile(batch_data: dict) -> str:
    profile = batch_data.get('display_profile') or {}
    if isinstance(profile, dict):
        return str(profile.get('aspect_ratio') or profile.get('profile_id') or '')
    return ''


def expected_aspect_bounds(batch_data: dict) -> tuple[float, float]:
    profile = aspect_profile(batch_data)
    if '9:16' in profile or 'portrait' in profile:
        return (0.45, 0.85)
    return (1.2, 2.2)


def make_sheet(items: list[dict], output: Path, *, crop: bool = False, cols: int = 4, portrait: bool = False) -> None:
    thumb = ((220, 390) if portrait and not crop else (320, 180)) if not crop else (220, 220)
    pad = 12
    label_h = 36
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new('RGB', (pad + cols * (thumb[0] + pad), pad + rows * (label_h + thumb[1] + pad)), 'white')
    draw = ImageDraw.Draw(sheet)
    for idx, item in enumerate(items):
        row, col = divmod(idx, cols)
        x = pad + col * (thumb[0] + pad)
        y = pad + row * (label_h + thumb[1] + pad)
        draw.text((x, y), label_for(item), fill=(0, 0, 0))
        img = face_crop(Path(item['candidate']), thumb) if crop else fit_image(Path(item['candidate']), thumb)
        sheet.paste(img, (x, y + label_h))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)


def image_sanity_warnings(path: Path) -> list[dict]:
    warnings = []
    with Image.open(path) as im:
        gray = im.convert('L')
        stat = ImageStat.Stat(gray)
        mean = float(stat.mean[0])
        stdev = float(stat.stddev[0])
        hist = gray.histogram()
        pixels = max(gray.width * gray.height, 1)
        dark_ratio = sum(hist[:16]) / pixels
        light_ratio = sum(hist[240:]) / pixels
    if dark_ratio > 0.92 or mean < 8:
        warnings.append({'candidate': str(path), 'warning': 'mostly_black', 'mean_luma': round(mean, 2), 'dark_ratio': round(dark_ratio, 4)})
    if light_ratio > 0.92 or mean > 247:
        warnings.append({'candidate': str(path), 'warning': 'mostly_blank_white', 'mean_luma': round(mean, 2), 'light_ratio': round(light_ratio, 4)})
    if stdev < 3:
        warnings.append({'candidate': str(path), 'warning': 'low_detail_low_variance', 'luma_stdev': round(stdev, 2)})
    return warnings


def build_qa_summary(batch_data: dict, items: list[dict], output: Path, face_output: Path) -> dict:
    min_ratio, max_ratio = expected_aspect_bounds(batch_data)
    all_items = batch_data.get('items') or []
    candidate_dimensions = []
    warnings = []
    for item in items:
        path = Path(item['candidate'])
        with Image.open(path) as im:
            width, height = im.size
        if width < 256 or height < 144:
            warnings.append({'candidate': str(path), 'warning': 'too_small'})
        ratio = width / max(height, 1)
        if ratio < min_ratio or ratio > max_ratio:
            warnings.append({'candidate': str(path), 'warning': 'wrong_aspect_ratio', 'ratio': round(ratio, 4), 'expected_bounds': [min_ratio, max_ratio]})
        warnings.extend(image_sanity_warnings(path))
        candidate_dimensions.append({'candidate': str(path), 'width': width, 'height': height})
    return {
        'image_count': len(items),
        'missing_candidate_count': max(0, len(all_items) - len(items)),
        'aspect_profile': aspect_profile(batch_data),
        'expected_aspect_bounds': [min_ratio, max_ratio],
        'candidate_dimensions': candidate_dimensions,
        'face_crop_generated': face_output.exists(),
        'contact_sheet': str(output),
        'face_contact_sheet': str(face_output),
        'requires_owner_review': True,
        'promotion_status': batch_data.get('promotion_status') or 'not_promoted_pending_owner_approval',
        'warnings': warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch-summary', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--cols', type=int, default=4)
    args = parser.parse_args()

    batch_summary = Path(args.batch_summary).resolve()
    output = Path(args.output).resolve()
    batch_data = load_batch(batch_summary)
    items = load_items(batch_summary)
    portrait = '9:16' in aspect_profile(batch_data) or 'portrait' in aspect_profile(batch_data)
    make_sheet(items, output, crop=False, cols=args.cols, portrait=portrait)
    face_output = output.with_name(output.stem + '_face' + output.suffix)
    make_sheet(items, face_output, crop=True, cols=args.cols, portrait=portrait)
    qa_output = output.with_name(output.stem + '_qa_summary.json')
    qa_output.write_text(json.dumps(build_qa_summary(batch_data, items, output, face_output), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'CONTACT_SHEET {output}')
    print(f'FACE_CONTACT_SHEET {face_output}')
    print(f'QA_SUMMARY {qa_output}')
    print(f'ITEMS {len(items)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
