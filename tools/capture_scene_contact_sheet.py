
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'tools'
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from vn_product_config import build_project_paths, display_profile, renpy_dimensions, require_under  # noqa: E402
from validate_scene import SAFE_SCENE_ID_RE, ALLOWED_CAPTURE_KEYS, resolve_capture_warp, validate_capture_plan  # noqa: E402


def load_plan(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def find_window_for_pid(pid: int):
    import win32gui  # type: ignore
    import win32process  # type: ignore

    matches = []

    def enum(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        _, found = win32process.GetWindowThreadProcessId(hwnd)
        if found == pid:
            rect = win32gui.GetWindowRect(hwnd)
            title = win32gui.GetWindowText(hwnd)
            if rect[2] > rect[0] and rect[3] > rect[1]:
                matches.append((hwnd, rect, title))

    win32gui.EnumWindows(enum, None)
    if not matches:
        return None
    return max(matches, key=lambda item: (item[1][2] - item[1][0]) * (item[1][3] - item[1][1]))



def window_adjustment_plan(
    rect: tuple[int, int, int, int],
    *,
    target_window_size: tuple[int, int] | None = None,
    preserve_window_rect: bool = True,
    restore_window_rect: bool = True,
    force_position: tuple[int, int] | None = None,
) -> dict[str, Any]:
    original = list(rect)
    if preserve_window_rect or not target_window_size:
        return {
            'move_before_capture': False,
            'capture_rect': original,
            'target_rect': None,
            'restore_after_capture': False,
            'restore_rect': original,
            'preserve_window_rect': preserve_window_rect,
        }
    target_w, target_h = target_window_size
    x, y = force_position if force_position is not None else (rect[0], rect[1])
    target_rect = [int(x), int(y), int(x + target_w), int(y + target_h)]
    return {
        'move_before_capture': True,
        'capture_rect': target_rect,
        'target_rect': target_rect,
        'restore_after_capture': bool(restore_window_rect),
        'restore_rect': original,
        'preserve_window_rect': preserve_window_rect,
    }


def capture_window(pid: int, out_path: Path, *, target_window_size: tuple[int, int] | None = None, preserve_window_rect: bool = True, restore_window_rect: bool = True, force_position: tuple[int, int] | None = None) -> dict[str, Any]:
    from PIL import ImageGrab  # type: ignore
    import win32con  # type: ignore
    import win32gui  # type: ignore

    deadline = time.time() + 10
    info = None
    while time.time() < deadline:
        info = find_window_for_pid(pid)
        if info:
            break
        time.sleep(0.25)
    if not info:
        raise RuntimeError(f'No visible RenPy window found for pid {pid}')
    hwnd, rect, title = info
    adjustment = window_adjustment_plan(rect, target_window_size=target_window_size, preserve_window_rect=preserve_window_rect, restore_window_rect=restore_window_rect, force_position=force_position)
    target = {'width': target_window_size[0], 'height': target_window_size[1], 'reason': 'display_profile_phone_scaled'} if target_window_size else None
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        if adjustment['move_before_capture']:
            tr = adjustment['target_rect']
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, tr[0], tr[1], tr[2] - tr[0], tr[3] - tr[1], win32con.SWP_SHOWWINDOW)
            time.sleep(0.25)
        else:
            # Do not move or resize the window by default. Only foreground it for a stable crop.
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1], win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.6)
    rect = win32gui.GetWindowRect(hwnd)
    img = ImageGrab.grab(bbox=rect)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    if adjustment.get('restore_after_capture'):
        try:
            rr = adjustment['restore_rect']
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, rr[0], rr[1], rr[2] - rr[0], rr[3] - rr[1], win32con.SWP_SHOWWINDOW)
        except Exception:
            pass
    return {'title': title, 'window_rect': list(rect), 'target_window_size': target, 'captured_size': list(img.size), 'window_adjustment': adjustment}


KEY_VK = {
    'enter': 0x0D,
    'space': 0x20,
    'escape': 0x1B,
    'up': 0x26,
    'down': 0x28,
    'left': 0x25,
    'right': 0x27,
}


def focus_window_for_pid(pid: int):
    import win32con  # type: ignore
    import win32gui  # type: ignore

    deadline = time.time() + 10
    info = None
    while time.time() < deadline:
        info = find_window_for_pid(pid)
        if info:
            break
        time.sleep(0.25)
    if not info:
        raise RuntimeError(f'No visible RenPy window found for pid {pid}')
    hwnd, rect, title = info
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        width = max(1, rect[2] - rect[0])
        height = max(1, rect[3] - rect[1])
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, rect[0], rect[1], width, height, win32con.SWP_SHOWWINDOW)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.15)
    return hwnd, rect, title


def perform_pre_capture_actions(pid: int, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import win32api  # type: ignore
    import win32con  # type: ignore
    import win32gui  # type: ignore

    performed: list[dict[str, Any]] = []
    for action in actions:
        action_type = action.get('type')
        repeat = int(action.get('repeat', 1))
        interval = float(action.get('interval_seconds', action.get('post_wait_seconds', 0.15)))
        if action_type == 'wait':
            seconds = float(action.get('seconds', action.get('post_wait_seconds', 0.0)))
            time.sleep(seconds)
            performed.append({'type': 'wait', 'seconds': seconds})
            continue
        hwnd, rect, _title = focus_window_for_pid(pid)
        if action_type == 'key':
            key = str(action.get('key'))
            if key not in ALLOWED_CAPTURE_KEYS or key not in KEY_VK:
                raise RuntimeError(f'unsupported pre_capture key: {key}')
            vk = KEY_VK[key]
            for _ in range(repeat):
                win32gui.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, 0)
                time.sleep(0.03)
                win32gui.PostMessage(hwnd, win32con.WM_KEYUP, vk, 0)
                # Also send a global key event as a fallback when the window manager
                # did grant foreground focus. The targeted PostMessage is the primary
                # path and avoids depending on focus for menu proof captures.
                try:
                    win32api.keybd_event(vk, 0, 0, 0)
                    time.sleep(0.01)
                    win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
                except Exception:
                    pass
                time.sleep(interval)
            performed.append({'type': 'key', 'key': key, 'repeat': repeat, 'interval_seconds': interval})
        elif action_type == 'click':
            x_frac = float(action.get('x'))
            y_frac = float(action.get('y'))
            x = int(rect[0] + (rect[2] - rect[0]) * x_frac)
            y = int(rect[1] + (rect[3] - rect[1]) * y_frac)
            for _ in range(repeat):
                rel_x = int((rect[2] - rect[0]) * x_frac)
                rel_y = int((rect[3] - rect[1]) * y_frac)
                lparam = (rel_y << 16) | rel_x
                win32gui.PostMessage(hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
                time.sleep(0.03)
                win32gui.PostMessage(hwnd, win32con.WM_LBUTTONUP, 0, lparam)
                try:
                    win32api.SetCursorPos((x, y))
                    time.sleep(0.01)
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    time.sleep(0.01)
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                except Exception:
                    pass
                time.sleep(interval)
            performed.append({'type': 'click', 'x': x_frac, 'y': y_frac, 'repeat': repeat, 'interval_seconds': interval})
        else:
            raise RuntimeError(f'unsupported pre_capture action type: {action_type}')
    return performed


def capture_actions(cap: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize legacy `advance` plus explicit pre-capture actions.

    Capture plans historically used `advance` to mean repeated dialogue
    advances, but runtime capture only executed `pre_capture_actions`. Keep the
    shorthand by translating it to Enter key actions before any explicit actions.
    """
    actions: list[dict[str, Any]] = []
    advance = int(cap.get('advance', 0) or 0)
    if advance > 0:
        actions.append({'type': 'key', 'key': 'enter', 'repeat': advance, 'interval_seconds': 0.15})
    raw_actions = cap.get('pre_capture_actions') or []
    if isinstance(raw_actions, list):
        actions.extend(raw_actions)
    return actions



def analyze_screenshot_quality(path: Path, *, allow_blank: bool = False) -> dict[str, Any]:
    """Detect accidental black/blank captures from bad Ren'Py warp timing.

    The window title/chrome can make a fully black game frame look non-black if
    the whole screenshot is averaged, so analyze the central gameplay area and
    ignore a small top band.
    """
    from PIL import Image, ImageStat  # type: ignore

    with Image.open(path) as img:
        rgb = img.convert('RGB')
        width, height = rgb.size
        left = int(width * 0.04)
        top = int(height * 0.08)
        right = int(width * 0.96)
        bottom = int(height * 0.96)
        if right <= left or bottom <= top:
            region = rgb
        else:
            region = rgb.crop((left, top, right, bottom))
        gray = region.convert('L')
        stat = ImageStat.Stat(gray)
        mean = float(stat.mean[0])
        stdev = float(stat.stddev[0])
        hist = gray.histogram()
        total = max(1, sum(hist))
        dark_ratio = sum(hist[:16]) / total
        light_ratio = sum(hist[240:]) / total

    metrics = {
        'mean_luma': round(mean, 3),
        'stdev_luma': round(stdev, 3),
        'dark_ratio': round(dark_ratio, 6),
        'light_ratio': round(light_ratio, 6),
        'crop': {'left_pct': 0.04, 'top_pct': 0.08, 'right_pct': 0.96, 'bottom_pct': 0.96},
    }
    if allow_blank:
        return {'status': 'PASS', 'reason': 'blank_allowed', **metrics}
    if (mean <= 12 and stdev <= 10) or (dark_ratio >= 0.94 and mean <= 30):
        return {'status': 'FAIL', 'reason': 'mostly_black_frame', **metrics}
    if mean >= 245 and stdev <= 6 and light_ratio >= 0.94:
        return {'status': 'FAIL', 'reason': 'mostly_blank_white_frame', **metrics}
    return {'status': 'PASS', 'reason': 'content_present', **metrics}


def make_contact_sheet(images: list[Path], labels: list[str], out_path: Path) -> None:
    from PIL import Image, ImageDraw  # type: ignore

    loaded = [Image.open(p).convert('RGB') for p in images]
    if not loaded:
        raise RuntimeError('no screenshots captured')
    thumb_w = 480
    thumb_h = int(thumb_w * loaded[0].height / loaded[0].width)
    pad = 28
    cols = min(3, len(loaded))
    rows = (len(loaded) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * thumb_w, rows * (thumb_h + pad)), 'white')
    draw = ImageDraw.Draw(sheet)
    for idx, img in enumerate(loaded):
        thumb = img.resize((thumb_w, thumb_h))
        x = (idx % cols) * thumb_w
        y = (idx // cols) * (thumb_h + pad)
        sheet.paste(thumb, (x, y + pad))
        draw.text((x + 6, y + 6), labels[idx], fill=(0, 0, 0))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Generic RenPy scene contact-sheet capture from a capture plan.')
    parser.add_argument('--project-root', default=None)
    parser.add_argument('--contract')
    parser.add_argument('--scene-id', required=True)
    parser.add_argument('--capture-plan', required=True)
    parser.add_argument('--out-dir', default='')
    parser.add_argument('--dry-run', action='store_true', help='Validate plan and print intended captures without launching RenPy.')
    parser.add_argument('--runtime-timeout', type=int, default=120, help='Overall timeout seconds for each RenPy capture process.')
    parser.add_argument('--allow-blank-captures', action='store_true', help='Allow intentional black/blank captures. Default fails closed on likely bad warp timing.')
    parser.add_argument('--phone-scale-window', action='store_true', help='Force a scaled 9:16-ish RenPy window that fits on desktop before capture.')
    parser.add_argument('--viewport-width', type=int, default=0, help='Optional target RenPy/profile width for capture window scaling.')
    parser.add_argument('--viewport-height', type=int, default=0, help='Optional target RenPy/profile height for capture window scaling.')
    parser.add_argument('--move-window-for-capture', action='store_true', help='Opt in to moving/resizing the RenPy window for capture. Default preserves the current window rect.')
    parser.add_argument('--no-restore-window-rect', action='store_true', help='Do not restore the original window rect after an opt-in move/resize.')
    parser.add_argument('--force-window-position', default='', help='Optional x,y window position used only with --move-window-for-capture.')
    args = parser.parse_args(argv)


    if not SAFE_SCENE_ID_RE.match(args.scene_id):
        print(f'CAPTURE_SCENE_REFUSED: unsafe scene_id: {args.scene_id}')
        return 2
    paths = build_project_paths(args.project_root, args.contract)
    plan_path = Path(args.capture_plan).resolve()
    try:
        require_under(plan_path, paths.project_root, 'capture plan')
    except ValueError as exc:
        print('CAPTURE_SCENE_REFUSED:', exc)
        return 2
    out_dir = Path(args.out_dir).resolve() if args.out_dir else (paths.project_root / 'docs/validation' / args.scene_id / 'gameplay_screenshots').resolve()
    try:
        require_under(out_dir, paths.project_root, 'capture output directory')
    except ValueError as exc:
        print('CAPTURE_SCENE_REFUSED:', exc)
        return 2

    gate = validate_capture_plan(plan_path, args.scene_id, paths.project_root)
    if gate['status'] != 'PASS':
        print('CAPTURE_SCENE_FAILED: capture plan invalid')
        for err in gate.get('errors', []):
            print('-', err)
        return 1
    try:
        plan = load_plan(plan_path)
    except Exception as exc:
        print(f'CAPTURE_SCENE_FAILED: cannot read capture plan: {exc}')
        return 1
    captures = plan['captures']
    print('CAPTURE_SCENE_CONTACT_SHEET')
    print('scene_id', args.scene_id)
    print('captures', len(captures))
    if args.dry_run:
        print('dry_run true')
        for cap in captures:
            actions = cap.get('pre_capture_actions') or []
            suffix = f" actions={len(actions)}" if actions else ''
            print('capture', cap.get('name'), resolve_capture_warp(cap, paths.project_root), suffix)
        return 0

    if sys.platform != 'win32':
        print('CAPTURE_SCENE_REFUSED: runtime capture currently requires Windows window APIs')
        return 2
    try:
        import PIL  # noqa: F401
        import win32gui  # noqa: F401
        import win32process  # noqa: F401
        import win32con  # noqa: F401
    except Exception as exc:
        print(f'CAPTURE_SCENE_REFUSED: runtime capture dependencies missing: {exc}')
        return 2
    profile = display_profile(paths.contract)
    renpy_w, renpy_h = renpy_dimensions(paths.contract)
    viewport_w = args.viewport_width or renpy_w
    viewport_h = args.viewport_height or renpy_h
    use_phone_scale = args.phone_scale_window or viewport_h > viewport_w or str(profile.get('aspect_ratio')) == '9:16'
    force_position = None
    if args.force_window_position:
        try:
            fx, fy = args.force_window_position.split(',', 1)
            force_position = (int(fx), int(fy))
        except Exception:
            print('CAPTURE_SCENE_REFUSED: --force-window-position must be x,y')
            return 2
    target_window_size = None
    if use_phone_scale:
        # Keep a phone-shaped window on-screen; actual RenPy internal resolution is still controlled by the game.
        target_w = 430
        target_h = max(1, int(round(target_w * viewport_h / max(1, viewport_w))))
        target_window_size = (target_w, target_h)
    renpy = paths.contract.get('renpy_sdk_exe')
    renpy_path = Path(renpy) if renpy else None
    if not renpy_path or not renpy_path.exists() or not renpy_path.is_file():
        print('CAPTURE_SCENE_REFUSED: renpy_sdk_exe missing or not found')
        return 2

    screenshots: list[Path] = []
    labels: list[str] = []
    quality_results: list[dict[str, Any]] = []
    for idx, cap in enumerate(captures, 1):
        name = cap.get('name') or f'capture_{idx:02d}'
        warp = resolve_capture_warp(cap, paths.project_root)
        if not warp:
            print(f'CAPTURE_SCENE_FAILED: cannot resolve warp for {name}')
            return 1
        out = (out_dir / f'{idx:02d}_{name}.png').resolve()
        try:
            require_under(out, out_dir, 'screenshot output')
        except ValueError as exc:
            print('CAPTURE_SCENE_REFUSED:', exc)
            return 2
        proc = subprocess.Popen([str(renpy_path), str(paths.project_root), '--warp', warp], cwd=paths.project_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            wait = float(cap.get('wait_seconds', 3.0))
            deadline = time.time() + args.runtime_timeout
            time.sleep(wait)
            if time.time() > deadline:
                raise TimeoutError(f'capture {name} exceeded timeout before screenshot')
            actions = capture_actions(cap)
            performed_actions = perform_pre_capture_actions(proc.pid, actions) if actions else []
            if time.time() > deadline:
                raise TimeoutError(f'capture {name} exceeded timeout before screenshot')
            capture_meta = capture_window(proc.pid, out, target_window_size=target_window_size, preserve_window_rect=not args.move_window_for_capture, restore_window_rect=not args.no_restore_window_rect, force_position=force_position)
            quality = analyze_screenshot_quality(out, allow_blank=bool(cap.get('allow_blank') or args.allow_blank_captures))
            quality_result = {'name': name, 'path': str(out), 'warp': warp, 'pre_capture_actions': performed_actions, 'capture_meta': capture_meta, **quality}
            quality_results.append(quality_result)
            if quality['status'] != 'PASS':
                qa_path = out_dir / 'capture_quality_failed.json'
                qa_path.write_text(json.dumps(quality_results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                raise RuntimeError(
                    f"capture {name} failed image quality gate: {quality['reason']} "
                    f"mean={quality['mean_luma']} stdev={quality['stdev_luma']} "
                    f"dark_ratio={quality['dark_ratio']} light_ratio={quality['light_ratio']}"
                )
            if proc.poll() not in (None, 0):
                stdout, stderr = proc.communicate(timeout=1)
                raise RuntimeError(f'RenPy exited with {proc.returncode}: {stderr or stdout}')
            for err_file in ['traceback.txt', 'errors.txt']:
                err_path = paths.project_root / err_file
                if err_path.exists():
                    raise RuntimeError(f'RenPy runtime error file detected: {err_path}')
        except Exception as exc:
            print(f'CAPTURE_SCENE_FAILED: {exc}')
            return 1
        finally:
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        screenshots.append(out)
        labels.append(name)
        print('captured', name, out)
    sheet = out_dir / f'{args.scene_id}_contact_sheet.png'
    make_contact_sheet(screenshots, labels, sheet)
    failed_quality = [item for item in quality_results if item.get('status') != 'PASS']
    manifest = {
        'scene_id': args.scene_id,
        'capture_plan': str(plan_path),
        'screenshots': [str(p) for p in screenshots],
        'contact_sheet': str(sheet),
        'display_profile': profile,
        'viewport': {'width': viewport_w, 'height': viewport_h, 'phone_scale_window': use_phone_scale, 'target_window_size': list(target_window_size) if target_window_size else None},
        'image_quality': quality_results,
        'image_quality_status': 'PASS' if not failed_quality else 'FAIL',
    }
    (out_dir / 'capture_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('contact_sheet', sheet)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
