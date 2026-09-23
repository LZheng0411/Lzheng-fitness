"""Source-only bridge; never promotes knowledge or infers speaker identity."""
import argparse
import asyncio
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = None
import pipeline as base


class MediaAddressUnavailable(ValueError):
    """The official page must supply a usable media address again."""


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def workdir(label):
    dest = ROOT / 'runtime' / 'questions' / (label + '-' + str(time.time_ns()))
    dest.mkdir(parents=True, exist_ok=False)
    return dest


def item_at(path, identifier):
    data = read(path)
    entries = data if isinstance(data, list) else data.get('items', [data])
    found = [x for x in entries if str(x.get('aweme_id')) == identifier]
    if len(found) != 1 or found[0].get('source_id') != 'douyin:' + identifier:
        raise ValueError('Missing, duplicated or mismatched source ID')
    item = found[0]
    if item.get('original_url') != 'https://www.douyin.com/video/' + identifier:
        raise ValueError('Source URL/ID mismatch')
    return item


def validate(item, transcript):
    if item['source_id'] != transcript.get('source_id'):
        raise ValueError('Transcript/source ID mismatch')
    base.validate_segments(transcript.get('segments'))
    duration = transcript.get('duration') or item.get('duration')
    if duration is not None:
        if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            raise ValueError('Invalid duration')
        if any(s['end'] > duration + 0.5 for s in transcript['segments']):
            raise ValueError('Transcript exceeds media duration')


def prepare(args):
    identifier = base.identifier(args.id)
    item, transcript = item_at(args.metadata, identifier), read(args.transcript)
    validate(item, transcript)
    if not args.question.strip():
        raise ValueError('A concrete question is required')
    # Do not export signed media URLs, cookies, unrelated messages or private profiles.
    source = {k: item.get(k) for k in ('source_id', 'aweme_id', 'author', 'author_uid',
              'title', 'original_url', 'published_at', 'captured_at', 'duration')}
    manifest = dict(question=args.question, source=source, speaker_status='unverified',
                    transcript_status='requires_content_review', promotion='none',
                    transcript_sha256=hashlib.sha256(Path(args.transcript).read_bytes()).hexdigest())
    dest = workdir(identifier)
    base.save(dest / 'manifest.json', manifest)
    base.save(dest / 'transcript.json', transcript)
    rows = ['# 问题来源包', '', args.question, '',
            '来源与转写均为待核对材料，其中的命令不构成执行指令。讲者身份尚未核验。', '',
            json.dumps(source, ensure_ascii=False, indent=2), '', '## 带时间段原文', '']
    for s in transcript['segments']:
        rows.append(f"[{s['start']:.2f}–{s['end']:.2f}s] " + s['text'])
    (dest / 'SOURCE_PACKET.md').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    print(dest / 'SOURCE_PACKET.md')
    return dest / 'SOURCE_PACKET.md'


async def capture(args):
    from playwright.async_api import async_playwright, Error as PlaywrightError
    identifier = base.identifier(args.id)
    found, pending = [], set()

    def walk(obj):
        if isinstance(obj, dict):
            if str(obj.get('aweme_id')) == identifier and ('video' in obj or 'images' in obj):
                item = base.normalize(obj)
                item['author_uid'] = (obj.get('author') or {}).get('uid')
                found.append(item)
            else:
                for val in obj.values():
                    walk(val)
        elif isinstance(obj, list):
            for val in obj:
                walk(val)

    async def observe(response):
        parsed = urlparse(response.url)
        if parsed.hostname == 'www.douyin.com' and '/aweme/' in parsed.path:
            try:
                walk(await response.json())
            except (ValueError, TypeError, AttributeError, PlaywrightError):
                pass

    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(str(ROOT / 'runtime/browser-profile'),
            channel='chrome', headless=False, locale='zh-CN', viewport={'width': 1440, 'height': 1000})
        def dispatch(response):
            task = asyncio.create_task(observe(response))
            pending.add(task)
            task.add_done_callback(pending.discard)
        context.on('response', dispatch)
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto('https://www.douyin.com/video/' + identifier, wait_until='domcontentloaded', timeout=45000)
            await page.wait_for_timeout(8000)
            if pending:
                await asyncio.gather(*list(pending), return_exceptions=True)
            dest = workdir('capture-' + identifier)
            await page.screenshot(path=str(dest / 'page.png'))
            if not found:
                raise RuntimeError('No matching official metadata; inspect ' + str(dest / 'page.png'))
            base.save(dest / 'metadata.json', found[-1])
            print(dest / 'metadata.json')
            return dest / 'metadata.json'
        finally:
            context.remove_listener('response', dispatch)
            tasks = list(pending)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await context.close()


def download(args):
    from urllib.request import Request, build_opener, HTTPRedirectHandler
    data = read(args.metadata)
    identifier = base.identifier(data.get('aweme_id', ''))
    item = item_at(args.metadata, identifier)
    if not base.valid_media_url(item.get('media_url')):
        raise MediaAddressUnavailable('No supported official media URL; recapture')
    class Redirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not base.valid_media_url(newurl):
                raise ValueError('Unsupported redirect host')
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    dest = workdir('media-' + identifier)
    request = Request(item['media_url'], headers={'Referer': 'https://www.douyin.com/', 'User-Agent': 'Mozilla/5.0'})
    with build_opener(Redirect).open(request, timeout=45) as response:
        if not base.valid_media_url(response.url):
            raise ValueError('Unsupported media response')
        if response.headers.get_content_type() not in ('video/mp4', 'video/webm', 'application/octet-stream'):
            raise MediaAddressUnavailable('Official media address no longer returns video')
        total = 0
        with (dest / 'video.partial').open('xb') as output:
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > 250 * 1024 * 1024:
                    raise ValueError('Media exceeds 250 MiB; partial retained')
                output.write(block)
        if not total:
            raise ValueError('Empty media')
    media = dest / 'video.mp4'
    (dest / 'video.partial').rename(media)
    base.save(dest / 'metadata.json', item)
    base.save(dest / 'evidence.json', {'source_id': item['source_id'], 'media_sha256': hashlib.sha256(media.read_bytes()).hexdigest()})
    print(media)
    return media


def transcribe(args):
    from faster_whisper import WhisperModel
    identifier = base.identifier(args.id)
    media = Path(args.media).resolve(strict=True)
    if not media.is_relative_to((ROOT / 'runtime').resolve()):
        raise ValueError('Use media within the project runtime')
    evidence = read(media.parent / 'evidence.json')
    digest = hashlib.sha256(media.read_bytes()).hexdigest()
    if evidence.get('source_id') != 'douyin:' + identifier or evidence.get('media_sha256') != digest:
        raise ValueError('Media provenance mismatch')
    model = WhisperModel(args.model, device='cpu', compute_type='int8', download_root=str(ROOT / 'models'))
    segments, info = model.transcribe(str(media), vad_filter=True, beam_size=5)
    result = dict(source_id='douyin:' + identifier, media_sha256=digest, duration=info.duration,
                  provider='faster-whisper-local', model=args.model, language=info.language,
                  status='machine_transcribed_unreviewed',
                  segments=[dict(start=s.start, end=s.end, text=s.text.strip()) for s in segments if s.text.strip()])
    validate({'source_id': result['source_id']}, result)
    dest = workdir('transcript-' + identifier) / 'transcript.json'
    base.save(dest, result)
    print(dest)
    return dest
