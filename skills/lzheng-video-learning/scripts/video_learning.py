"""Portable, resumable source preparation. Semantic learning remains with the Agent."""
from __future__ import annotations
import argparse, asyncio, contextlib, hashlib, json, os, sys
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
import pipeline as base
import question_tools as source

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def valid_artifact(entry, kind):
    item=entry.get(kind) or {}
    p=Path(item.get('path',''))
    return p.is_file() and fingerprint(p)==item.get('sha256')

def remember(entry, kind, path):
    entry[kind]={'path':str(Path(path).resolve()),'sha256':fingerprint(path)}

def refreshable_address_error(error):
    return (isinstance(error,source.MediaAddressUnavailable) or
            isinstance(error,HTTPError) and error.code in (401,403,404,410))

def capture_metadata(s,entry,identifier,runtime):
    # Forget unusable pointers before capture so a failed refresh cannot pin retries
    # to an old URL. Existing files remain on disk for inspection.
    for kind in ('metadata','media','transcript','packet'):entry.pop(kind,None)
    base.save(runtime/'learning-state.json',s)
    metadata=asyncio.run(source.capture(SimpleNamespace(id=identifier)))
    remember(entry,'metadata',metadata)
    base.save(runtime/'learning-state.json',s)

def capture_selected(args,runtime):
    identifier=base.identifier(args.id)
    metadata=asyncio.run(source.capture(SimpleNamespace(id=identifier)))
    s=state(runtime);entry=s['works'].get(identifier)
    if entry is not None:
        remember(entry,'metadata',metadata)
        # A new source snapshot needs a new packet, but verified media and its
        # transcript can still be reused for this same work ID.
        entry.pop('packet',None);entry.pop('question_sha256',None)
        entry.update(content_reviewed=False,user_mastery='unknown')
        if entry.get('status')!='failed':entry['status']='selected'
        base.save(runtime/'learning-state.json',s)
    return metadata

def paths(args):
    root=Path(args.workspace).expanduser().resolve()
    installed=Path(__file__).resolve().parents[1]
    if root==installed or installed in root.parents:
        raise ValueError('Use a private workspace outside the installed Skill')
    root.mkdir(parents=True,exist_ok=True)
    base.ROOT=source.ROOT=root
    base.RUNTIME=root/'runtime';base.RUNTIME.mkdir(exist_ok=True)
    return base.RUNTIME

@contextlib.contextmanager
def lock(runtime):
    path=runtime/'learning.lock'
    try:
        with path.open('x',encoding='utf-8') as f:f.write(str(os.getpid()))
    except FileExistsError:
        raise ValueError('Another operation owns learning.lock; after a crash check its PID before removing it')
    try:yield
    finally:path.unlink(missing_ok=True)

def state(runtime):
    p=runtime/'learning-state.json'
    return read(p) if p.exists() else {'schema':1,'works':{}}

def candidates(args,runtime):
    rows=read(runtime/'collection.json').get('items',[])
    rows=[r for r in rows if (not args.author or args.author.casefold() in str(r.get('author','')).casefold() or args.author==str(r.get('author_uid',''))) and (not args.topic or args.topic.casefold() in str(r.get('title','')).casefold())]
    print(json.dumps([{k:r.get(k) for k in ('aweme_id','author','author_uid','title','original_url')} for r in rows],ensure_ascii=False))

def select(args,runtime):
    rows=read(args.input)
    if not isinstance(rows,list) or not rows:raise ValueError('Selection must be a nonempty JSON array of IDs or objects with aweme_id')
    ids=[]
    for row in rows:
        identifier=base.identifier(row.get('aweme_id') if isinstance(row,dict) else row)
        if identifier not in ids:ids.append(identifier)
    question=args.question.strip()
    if not question:raise ValueError('A learning question is required')
    s=state(runtime)
    for identifier in ids:s['works'].setdefault(identifier,{'status':'selected','attempts':0})
    s['selection']=ids;s['question']=question
    base.save(runtime/'learning-state.json',s)
    print(json.dumps({'selected':len(ids),'question':question},ensure_ascii=False))

def batch(args,runtime):
    s=state(runtime)
    if not s.get('selection'):raise ValueError('Select a scope first')
    question=s['question'];question_hash=hashlib.sha256(question.encode()).hexdigest()
    processed=0
    for identifier in s['selection']:
        e=s['works'][identifier]
        if e.get('status')=='failed' and not args.retry_failed:continue
        if e.get('question_sha256')==question_hash and e.get('model')==args.model and all(valid_artifact(e,k) for k in ('metadata','media','transcript','packet')):continue
        if processed>=args.limit:break
        processed+=1;e['attempts']+=1;e['status']='preparing'
        base.save(runtime/'learning-state.json',s)
        try:
            if not valid_artifact(e,'metadata'):
                capture_metadata(s,e,identifier,runtime)
            if not valid_artifact(e,'media'):
                try:
                    media=source.download(SimpleNamespace(metadata=e['metadata']['path']))
                except Exception as error:
                    if not refreshable_address_error(error):raise
                    capture_metadata(s,e,identifier,runtime)
                    try:
                        media=source.download(SimpleNamespace(metadata=e['metadata']['path']))
                    except Exception as retry_error:
                        if refreshable_address_error(retry_error):e.pop('metadata',None)
                        raise
                remember(e,'media',media)
                for k in ('transcript','packet'):e.pop(k,None)
                base.save(runtime/'learning-state.json',s)
            if not valid_artifact(e,'transcript') or e.get('model')!=args.model:
                transcript=source.transcribe(SimpleNamespace(id=identifier,media=e['media']['path'],model=args.model))
                remember(e,'transcript',transcript);e['model']=args.model;e.pop('packet',None)
                base.save(runtime/'learning-state.json',s)
            packet=source.prepare(SimpleNamespace(id=identifier,metadata=e['metadata']['path'],transcript=e['transcript']['path'],question=question))
            remember(e,'packet',packet)
            e.update(status='source_ready',question_sha256=question_hash,error=None,content_reviewed=False,user_mastery='unknown')
        except Exception as exc:
            # Do not put signed media URLs or browser state in an error report.
            e.update(status='failed',error=type(exc).__name__+': check source, login or local files; use batch --retry-failed after resolving')
        finally:base.save(runtime/'learning-state.json',s)
    print(json.dumps({'processed':processed,'states':{i:s['works'][i]['status'] for i in s['selection']}},ensure_ascii=False))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',required=True)
    sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('scan');q.add_argument('--max-items',type=int,default=40);q.add_argument('--timeout',type=int,default=300);q.add_argument('--auto-scroll',action='store_true')
    q=sub.add_parser('candidates');q.add_argument('--author');q.add_argument('--topic')
    q=sub.add_parser('select');q.add_argument('--input',required=True);q.add_argument('--question',required=True)
    q=sub.add_parser('batch');q.add_argument('--limit',type=int,default=5);q.add_argument('--model',default='small');q.add_argument('--retry-failed',action='store_true')
    q=sub.add_parser('capture');q.add_argument('--id',required=True)
    q=sub.add_parser('download');q.add_argument('--metadata',required=True)
    q=sub.add_parser('transcribe');q.add_argument('--id',required=True);q.add_argument('--media',required=True);q.add_argument('--model',default='small')
    q=sub.add_parser('prepare')
    for name in ('id','metadata','transcript','question'):q.add_argument('--'+name,required=True)
    sub.add_parser('status')
    a=p.parse_args()
    if a.command=='batch' and not 1<=a.limit<=100:p.error('--limit must be 1..100; resume further batches')
    if a.command=='scan' and (not 1<=a.max_items<=10000 or not 1<=a.timeout<=1200):p.error('scan bounds: 1..10000 items, 1..1200 seconds')
    runtime=paths(a)
    if a.command=='status':
        s=state(runtime);print(json.dumps({'question':s.get('question'),'works':{i:{k:v.get(k) for k in ('status','attempts','error','content_reviewed','user_mastery')} for i,v in s['works'].items()}},ensure_ascii=False));return
    if a.command=='candidates':candidates(a,runtime);return
    with lock(runtime):
        if a.command=='scan':asyncio.run(base.scan(a))
        elif a.command=='capture':capture_selected(a,runtime)
        elif a.command in ('download','transcribe','prepare'):getattr(source,a.command)(a)
        else:globals()[a.command](a,runtime)

if __name__=='__main__':main()
