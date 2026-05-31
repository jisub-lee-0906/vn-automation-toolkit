from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.webp'}
AUDIO_EXTS = {'.ogg', '.mp3', '.wav', '.flac'}


def png_info(path: Path) -> dict[str, Any]:
    with path.open('rb') as f:
        sig = f.read(8)
        if sig != b'\x89PNG\r\n\x1a\n':
            raise ValueError('invalid_png_signature')
        length = struct.unpack('>I', f.read(4))[0]
        chunk_type = f.read(4)
        if chunk_type != b'IHDR' or length < 13:
            raise ValueError('missing_png_ihdr')
        data = f.read(13)
    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack('>IIBBBBB', data)
    return {
        'width': width,
        'height': height,
        'bit_depth': bit_depth,
        'png_color_type': color_type,
        'has_alpha': color_type in {4, 6},
        'png_compression': compression,
        'png_filter': filter_method,
        'png_interlace': interlace,
    }


def jpeg_info(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if not data.startswith(b'\xff\xd8'):
        raise ValueError('invalid_jpeg_signature')
    i = 2
    while i < len(data):
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            break
        marker = data[i]
        i += 1
        if marker in {0xD8, 0xD9}:
            continue
        if i + 2 > len(data):
            break
        seg_len = struct.unpack('>H', data[i:i+2])[0]
        if marker in set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0)):
            if i + 7 > len(data):
                break
            height = struct.unpack('>H', data[i+3:i+5])[0]
            width = struct.unpack('>H', data[i+5:i+7])[0]
            return {'width': width, 'height': height, 'has_alpha': False}
        i += seg_len
    raise ValueError('jpeg_dimensions_not_found')


def webp_info(path: Path) -> dict[str, Any]:
    data = path.read_bytes()[:64]
    if len(data) < 16 or data[:4] != b'RIFF' or data[8:12] != b'WEBP':
        raise ValueError('invalid_webp_signature')
    # Minimal support. VP8X contains canvas size minus one at bytes 24..29.
    if data[12:16] == b'VP8X' and len(data) >= 30:
        flags = data[20]
        width = 1 + int.from_bytes(data[24:27], 'little')
        height = 1 + int.from_bytes(data[27:30], 'little')
        return {'width': width, 'height': height, 'has_alpha': bool(flags & 0b00010000)}
    return {'width': None, 'height': None, 'has_alpha': None, 'warnings': ['webp_dimensions_not_parsed_for_this_subtype']}


def ffprobe_info(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not shutil.which('ffprobe'):
        return {}, ['ffprobe_unavailable']
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration:stream=codec_name,codec_type',
        '-of', 'json', str(path),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=30)
    if proc.returncode != 0:
        return {}, [f'ffprobe_failed:{proc.stderr.strip() or proc.stdout.strip()}']
    data = json.loads(proc.stdout or '{}')
    out: dict[str, Any] = {}
    if 'format' in data and 'duration' in data['format']:
        try:
            out['duration_seconds'] = float(data['format']['duration'])
        except Exception:
            out['duration_seconds'] = data['format']['duration']
    streams = data.get('streams') or []
    out['streams'] = streams
    if streams:
        out['codec_names'] = [s.get('codec_name') for s in streams if s.get('codec_name')]
        out['codec_types'] = [s.get('codec_type') for s in streams if s.get('codec_type')]
    return out, []


def inspect_asset(path: Path, asset_type: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        'tool': 'qa_asset_file',
        'checked_at': datetime.now().isoformat(timespec='seconds'),
        'path': str(path),
        'asset_type': asset_type,
        'status': 'fail',
        'errors': [],
        'warnings': [],
    }
    if not path.exists():
        result['errors'].append('file_missing')
        return result
    if not path.is_file():
        result['errors'].append('not_a_file')
        return result
    size = path.stat().st_size
    result['size_bytes'] = size
    result['extension'] = path.suffix.lower()
    if size <= 0:
        result['errors'].append('file_empty')
        return result

    ext = path.suffix.lower()
    try:
        if ext == '.png':
            result.update(png_info(path))
        elif ext in {'.jpg', '.jpeg'}:
            result.update(jpeg_info(path))
        elif ext == '.webp':
            info = webp_info(path)
            result.update({k: v for k, v in info.items() if k != 'warnings'})
            result['warnings'].extend(info.get('warnings', []))
        elif ext in AUDIO_EXTS:
            info, warnings = ffprobe_info(path)
            result.update(info)
            result['warnings'].extend(warnings)
        else:
            result['errors'].append(f'unsupported_extension:{ext}')
    except Exception as e:
        result['errors'].append(f'inspect_failed:{type(e).__name__}:{e}')

    if result.get('width') and result.get('height'):
        result['aspect_ratio'] = round(result['width'] / result['height'], 6)
    if not result['errors']:
        result['status'] = 'pass'
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Inspect a VN asset file and write a machine-readable QA report.')
    parser.add_argument('path')
    parser.add_argument('--asset-type')
    parser.add_argument('--json-out')
    args = parser.parse_args(argv)

    report = inspect_asset(Path(args.path), args.asset_type)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print('QA_ASSET_FILE')
    print('status', report['status'])
    print('path', report['path'])
    if 'size_bytes' in report:
        print('size_bytes', report['size_bytes'])
    if report.get('width') and report.get('height'):
        print('dimensions', f"{report['width']}x{report['height']}")
        print('aspect_ratio', report.get('aspect_ratio'))
    if 'has_alpha' in report:
        print('has_alpha', report['has_alpha'])
    for warning in report.get('warnings', []):
        print('warning', warning)
    for error in report.get('errors', []):
        print('error', error)
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
