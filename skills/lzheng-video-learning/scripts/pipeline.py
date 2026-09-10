"""Local learning pipeline. No dependency on the proprietary collector core."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = None
RUNTIME = None


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def identifier(value):
    value = str(value)
    if not re.fullmatch(r'[0-9]{6,30}', value):
        raise ValueError('Invalid work ID')
    return value


def normalize(raw):
    work_id = identifier(raw.get('aweme_id', ''))
    author = raw.get('author') or {}
    video = raw.get('video') or {}
    created = raw.get('create_time')
    published = None
    if isinstance(created, (int, float)) and 0 < created < 32503680000:
        published = datetime.fromtimestamp(created, timezone.utc).isoformat()
    duration = video.get('duration')
    duration = duration / 1000 if isinstance(duration, (int, float)) and duration > 0 else None
    urls = (video.get('play_addr') or {}).get('url_list') or []
    return {
        'source_id': 'douyin:' + work_id, 'aweme_id': work_id,
        'author': author.get('nickname') or None, 'author_uid': author.get('uid'),
        'title': raw.get('desc') or None,
        'original_url': 'https://www.douyin.com/video/' + work_id,
        'published_at': published, 'captured_at': now(), 'duration': duration,
        'media_url': next((u for u in urls if valid_media_url(u)), None),
        'learning_status': '未学习', 'evidence_status': 'E0', 'promotion_status': 'raw',
    }


def valid_media_url(url):
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ''
        return (parsed.scheme == 'https' and not parsed.username and not parsed.password
                and any(host == d or host.endswith('.' + d)
                        for d in ('douyinvod.com', 'douyin.com', 'bytecdn.cn', 'bytecdn.com')))
    except (ValueError, TypeError):
        return False


async def scan(args):
    """Observe only the collection responses issued by the normal official page."""
    from playwright.async_api import async_playwright
    RUNTIME.mkdir(parents=True, exist_ok=True)
    items = {}
    snapshot = RUNTIME / 'collection.json'
    if snapshot.exists():
        previous = json.loads(snapshot.read_text(encoding='utf-8'))
        items = {x['aweme_id']: x for x in previous.get('items', [])}
    status_path = RUNTIME / 'browser-status.json'
    pending = set()
    authorized_response = False
    errors = []
    has_more = None
    last_scroll = 0
    scroll_count = 0
    last_response = 0
    run_snapshot = RUNTIME / 'scans' / (str(time.time_ns()) + '.json')

    def persist():
        manifest = {'captured_at': now(), 'source': 'own_collection', 'items': list(items.values())}
        save(run_snapshot, manifest)
        # A failed/new login must not erase a previously captured collection.
        if authorized_response or not snapshot.exists():
            save(snapshot, manifest)
        save(status_path, {'updated_at': now(), 'status': 'collection_observed' if authorized_response else 'waiting_for_user_login',
                           'metadata_count': len(items), 'max_items': args.max_items,
                           'media_downloads': 0, 'cloud_uploads': 0, 'parse_errors': errors[-3:],
                           'has_more': has_more, 'scroll_count': scroll_count})

    async def observe(response):
        nonlocal authorized_response, has_more, last_response
        parsed = urlparse(response.url)
        if parsed.hostname != 'www.douyin.com' or parsed.path != '/aweme/v1/web/aweme/listcollection/':
            return
        try:
            data = await response.json()
            if data.get('status_code') != 0 or not isinstance(data.get('aweme_list'), list):
                return
            authorized_response = True
            last_response = time.monotonic()
            has_more = bool(data.get('has_more'))
            for raw in data['aweme_list']:
                if len(items) >= args.max_items and str(raw.get('aweme_id')) not in items:
                    break
                try:
                    item = normalize(raw)
                    items[item['aweme_id']] = item
                except (ValueError, TypeError, AttributeError):
                    errors.append('invalid_item_metadata')
            persist()
        except Exception:
            errors.append('collection_response_unreadable')

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            str(RUNTIME / 'browser-profile'), channel='chrome', headless=False,
            locale='zh-CN', viewport={'width': 1280, 'height': 850})
        def dispatch(response):
            task = asyncio.create_task(observe(response))
            pending.add(task)
            task.add_done_callback(pending.discard)
        context.on('response', dispatch)
        page = context.pages[0] if context.pages else await context.new_page()
        persist()
        try:
            await page.goto('https://www.douyin.com/user/self?showTab=favorite_collection', wait_until='domcontentloaded', timeout=60000)
            print('BROWSER_READY: complete login yourself, then open 收藏. No media download.', flush=True)
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline and not page.is_closed():
                await asyncio.sleep(1)
                if (args.auto_scroll and authorized_response and has_more and len(items) < args.max_items
                        and time.monotonic() - last_scroll > 3 and scroll_count < 30):
                    # Scroll only the currently loaded official collection page. No private API requests.
                    await page.mouse.move(1000, 650)
                    await page.mouse.wheel(0, 900)
                    last_scroll = time.monotonic()
                    scroll_count += 1
                    persist()
                if (RUNTIME / 'stop-browser').exists():
                    break
                if (args.auto_scroll and authorized_response and time.monotonic() - last_response > 6
                        and (len(items) >= args.max_items or not has_more or scroll_count >= 30)):
                    break
            if pending:
                await asyncio.gather(*list(pending), return_exceptions=True)
            persist()
            save(status_path, {'updated_at': now(), 'status': 'browser_closed',
                               'collection_access_verified': authorized_response,
                               'metadata_count': len(items), 'media_downloads': 0, 'cloud_uploads': 0})
        finally:
            await context.close()


def transcribe(args):
    # Import locally only. Neither audio nor transcript is sent to a cloud provider.
    from faster_whisper import WhisperModel
    items = json.loads((RUNTIME / 'selected.json').read_text(encoding='utf-8'))['items']
    work_id = identifier(args.id)
    if work_id not in {x['aweme_id'] for x in items}:
        raise ValueError('Work has not been selected')
    media = Path(args.media).resolve(strict=True)
    media_root = (RUNTIME / 'media').resolve()
    if not media.is_relative_to(media_root):
        raise ValueError('Media must be in this project runtime/media directory')
    digest = hashlib.sha256(media.read_bytes()).hexdigest()
    destination = RUNTIME / 'transcripts' / (work_id + '-' + digest[:12] + '.json')
    if destination.exists():
        print('EXISTING_TRANSCRIPT: ' + str(destination))
        return
    model = WhisperModel(args.model, device='cpu', compute_type='int8', download_root=str(ROOT / 'models'))
    segments, info = model.transcribe(str(media), language='zh', vad_filter=True, beam_size=5)
    result = [{'start': s.start, 'end': s.end, 'text': s.text.strip()} for s in segments if s.text.strip()]
    validate_segments(result)
    save(destination, {'source_id': 'douyin:' + work_id, 'media_sha256': digest,
                       'provider': 'faster-whisper-local', 'model': args.model,
                       'transcribed_at': now(), 'duration': info.duration,
                       'status': 'machine_transcribed_unreviewed', 'segments': result})
    print('TRANSCRIBED: ' + str(destination))


def download(args):
    work_id = identifier(args.id)
    items = json.loads((RUNTIME / 'selected.json').read_text(encoding='utf-8'))['items']
    matches = [item for item in items if item['aweme_id'] == work_id]
    if len(matches) != 1 or not valid_media_url(matches[0].get('media_url')):
        raise ValueError('Missing selected work or approved media host; rescan the official page')
    class CheckedRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not valid_media_url(newurl):
                raise ValueError('Unexpected media redirect; inspect before continuing')
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    media_dir = RUNTIME / 'media'
    media_dir.mkdir(parents=True, exist_ok=True)
    media = media_dir / (work_id + '.mp4')
    if media.exists():
        print('EXISTING_MEDIA: ' + str(media))
        return
    partial = media_dir / (work_id + '-' + str(time.time_ns()) + '.partial')
    request = Request(matches[0]['media_url'], headers={'Referer': 'https://www.douyin.com/', 'User-Agent': 'Mozilla/5.0'})
    maximum = 250 * 1024 * 1024
    with build_opener(CheckedRedirect).open(request, timeout=45) as response:
        if not valid_media_url(response.url):
            raise ValueError('Unexpected media response host')
        if response.headers.get_content_type() not in ('video/mp4', 'application/octet-stream', 'video/webm'):
            raise ValueError('Response is not a supported video')
        total = 0
        with partial.open('xb') as output:
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > maximum:
                    raise ValueError('Video exceeds 250 MiB pilot limit; partial retained')
                output.write(block)
    if total == 0:
        raise ValueError('Empty media response')
    partial.rename(media)
    print('DOWNLOADED: ' + str(media))


def validate_segments(segments):
    if not isinstance(segments, list) or not segments:
        raise ValueError('No transcript segments')
    previous = 0
    for s in segments:
        start, end = s['start'], s['end']
        if (not isinstance(start, (int, float)) or not isinstance(end, (int, float))
            or not math.isfinite(start) or not math.isfinite(end) or start < previous
            or end <= start or not isinstance(s['text'], str) or not s['text'].strip()):
            raise ValueError('Invalid transcript timing or text')
        previous = start


def timestamp(seconds):
    milliseconds = round(seconds * 1000)
    return f'{milliseconds // 60000:02d}:{milliseconds // 1000 % 60:02d}.{milliseconds % 1000:03d}'
