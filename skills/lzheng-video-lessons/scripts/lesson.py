"""Build evidence-backed video lessons and register them without changing training facts."""
import argparse, hashlib, html, json, math, os, re, shutil, tempfile, urllib.request
from pathlib import Path
from datetime import datetime
ROOT=Path(__file__).resolve().parents[1]
ID=re.compile(r'^[a-z0-9][a-z0-9-]{0,79}$')
def require(ok,msg):
    if not ok: raise ValueError(msg)
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def dump(obj): return json.dumps(obj,ensure_ascii=False,indent=2)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def safe_json(x): return json.dumps(x,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
def text(x,name): require(isinstance(x,str) and x.strip(),name+' must be nonempty text')
def number(x): return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def validate(d):
    require(d.get('schema')==1,'schema must be 1');require(isinstance(d.get('id'),str) and ID.fullmatch(d['id']),'invalid lesson id')
    for k in ['title','author','verification','coverage_note']:text(d.get(k),k)
    require(d.get('source_type','url') in ['url','local'],'invalid source_type')
    if d.get('source_type','url')=='url':require(re.match(r'^https://[^/\s]+',d.get('source_url','')) is not None,'HTTPS source required')
    else:require(not d.get('source_url'),'local source must not expose filesystem paths')
    require(number(d.get('duration')) and d['duration']>0,'invalid duration')
    require(isinstance(d.get('chapters'),list) and d['chapters'],'chapters required')
    seen=set();last=0
    for c in d['chapters']:
        require(isinstance(c.get('id'),str) and ID.fullmatch(c['id']) and c['id'] not in seen,'duplicate/invalid chapter id');seen.add(c['id'])
        require(number(c.get('start')) and number(c.get('end')) and last<=c['start']<c['end']<=d['duration'],'overlapping/out-of-range chapter');last=c['end']
        require(c.get('verified') is True,'chapter needs content verification')
        for k in ['title','explain','caution']:text(c.get(k),k)
        require(isinstance(c.get('transcript'),str),'transcript must be source-check text (may be empty)')
        require(isinstance(c.get('points'),list) and c['points'] and all(isinstance(x,str) for x in c['points']),'points required')
        require(isinstance(c.get('details'),list) and len(c['details'])>=2,'at least two detailed steps')
        for step in c['details']:
            for k in ['title','text','evidence']:text(step.get(k),k)
            require(number(step.get('at')) and c['start']<=step['at']<c['end'],'step timestamp outside chapter')
    return d

def no_links(path):
    q=Path(path).absolute()
    for n in [q,*q.parents]:
        require(not n.is_symlink() and not (hasattr(n,'is_junction') and n.is_junction()),'symlink/junction not supported')
    return q

def manifest(folder,lesson):
    files=[{'path':p.relative_to(folder).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(folder.rglob('*')) if p.is_file()]
    (folder/'lesson-manifest.json').write_text(dump({'kind':'lzheng-video-lesson','schema':1,'lesson_id':lesson['id'],'files':files}),encoding='utf-8')
def build(a):
    d=validate(read(a.input));out=no_links(a.out);require(not out.exists(),'use a new output directory; existing lessons are preserved')
    media=Path(a.media).resolve() if a.media else None;poster=Path(a.poster).resolve() if a.poster else None
    if media: require(media.is_file() and media.suffix.lower()=='.mp4','readable MP4 required');text(d.get('media_rights_basis'),'media_rights_basis')
    if poster: require(media is not None and poster.is_file() and poster.suffix.lower() in ['.jpg','.jpeg','.png','.webp'],'poster requires media and an image')
    out.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='lesson-stage-',dir=out.parent))
    try:
        values={'TITLE':d['title'],'AUTHOR':d['author'],'DURATION':f"{int(d['duration']//60):02}:{int(d['duration']%60):02}",'COUNT':str(len(d['chapters'])),'SOURCE':d.get('source_url') or '#','ID':d['id'],'VERIFICATION':d['verification'],'COVERAGE':d['coverage_note']}
        page=(ROOT/'assets/lesson.html').read_text(encoding='utf-8')
        for k,v in values.items():page=page.replace('__'+k+'__',html.escape(v,quote=True))
        if d.get('source_type')=='local':page=page.replace('<a href="#" target="_blank" rel="noopener">打开抖音原视频 ↗</a>','<span>来源：用户提供的本地视频</span>')
        page=page.replace('__MEDIA__','<source src="video.mp4" type="video/mp4">' if media else '')
        page=page.replace('__POSTER__','poster="poster'+poster.suffix.lower()+'"' if poster else '')
        disabled="document.querySelector('.video-wrap').hidden=true;['play','replay','footerReplay','endReplay','segmentSeek','loop','mute'].forEach(id=>$(id).disabled=true);document.querySelectorAll('.jump').forEach(n=>n.disabled=true);"
        page=page.replace('__MEDIA_STATE__','' if media else disabled)
        if not media:
            page=page.replace("function select(i){", "function select(i){")
            page=page.replace("seek(c.start);progress();}","seek(c.start);progress();document.querySelectorAll('.jump').forEach(n=>n.disabled=true);$('playStatus').textContent='仅原视频链接 · 未提供可播放媒体，请打开原视频';}")
        (stage/'index.html').write_text(page,encoding='utf-8')
        # Data is external JS but remains literal JSON; never execute source snippets.
        payload=json.dumps(d['chapters'],ensure_ascii=False).replace('<','\\u003c')
        (stage/'chapters.js').write_text('window.LESSON_CHAPTERS = '+payload+';\n',encoding='utf-8')
        if media:shutil.copyfile(media,stage/'video.mp4')
        if poster:shutil.copyfile(poster,stage/('poster'+poster.suffix.lower()))
        (stage/'lesson.json').write_text(dump(d),encoding='utf-8');manifest(stage,d);stage.rename(out)
    except BaseException:
        # Only remove the newly-created staging tree, never the requested target.
        shutil.rmtree(stage,ignore_errors=True);raise
    return {'lesson_built':True,'integrated':False,'deployed':False,'directory':str(out),'playback':'local-media' if media else 'source-link'}

def verify_local(folder):
    folder=no_links(folder).resolve();m=read(folder/'lesson-manifest.json');require(m.get('kind')=='lzheng-video-lesson','unmanaged lesson')
    expected={'lesson-manifest.json'}
    for f in m['files']:
        rel=Path(f['path']);require(not rel.is_absolute() and '..' not in rel.parts,'unsafe manifest path');target=no_links(folder/rel).resolve();require(target.is_relative_to(folder),'outside lesson')
        require(target.is_file() and target.stat().st_size==f['bytes'] and sha(target)==f['sha256'],'lesson file changed: '+f['path']);expected.add(rel.as_posix())
    require({p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file()}==expected,'unexpected lesson files')
    return validate(read(folder/'lesson.json')),m

def integrate(a):
    file=no_links(a.html).resolve();lesson=no_links(a.lesson).resolve();d,_=verify_local(lesson);require(lesson.is_relative_to(file.parent),'lesson must be inside workbench directory')
    source=file.read_text(encoding='utf-8');require('id="m-knowledge"' in source,'knowledge page not found; upgrade existing template first')
    pat=re.compile(r'(<script[^>]*id="knowledge-lessons-data"[^>]*>)(.*?)(</script>)',re.S);match=pat.search(source)
    rows=json.loads(match.group(2)) if match else [];require(isinstance(rows,list),'invalid existing lesson registry')
    from urllib.parse import quote
    entry={'id':d['id'],'title':d['title'],'author':d['author'],'chapters':len(d['chapters']),'duration':f"{int(d['duration']//60):02}:{int(d['duration']%60):02}",'path':quote((lesson/'index.html').relative_to(file.parent).as_posix(),safe='/'),'source':d.get('source_url','')}
    legacy='id="knowledge-lessons-ui"' in source
    if legacy and rows and rows[0].get('id')==d['id']:
        require(all(rows[0].get(k)==entry[k] for k in ['title','author','chapters','duration']),'legacy first lesson has hardcoded labels; migrate that UI before changing metadata')
    existing=next((i for i,x in enumerate(rows) if x.get('id')==d['id']),None)
    if existing is None:rows.append(entry)
    else:rows[existing]=entry
    block=json.dumps(rows,ensure_ascii=False).replace('<','\\u003c')
    result=pat.sub(lambda m:m.group(1)+block+m.group(3),source) if match else source.replace('</body>','<script id="knowledge-lessons-data" type="application/json">'+block+'</script></body>')
    result=re.sub(r'<style id="portable-lessons-style">.*?</style>', '', result, flags=re.S)
    result=re.sub(r'<script id="portable-lessons-ui">.*?</script>', '', result, flags=re.S)
    result=result.replace('</body>',(ROOT/'assets/integration.html').read_text(encoding='utf-8')+'</body>')
    train=re.compile(r'<script id="workbench-data"[^>]*>.*?</script>',re.S)
    require(train.findall(source)==train.findall(result),'training data changed')
    if a.apply:
        backup=no_links(a.backup_dir);require(not backup.resolve().is_relative_to(lesson),'backup must be outside lesson');backup.mkdir(parents=True,exist_ok=True)
        shutil.copy2(file,backup/(datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'-'+file.name))
        fd,tmp=tempfile.mkstemp(prefix='lesson-integrate-',suffix='.tmp',dir=file.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(result)
            os.replace(tmp,file)
        finally:
            if Path(tmp).exists():Path(tmp).unlink()
    return {'integrated':bool(a.apply),'preflight':True,'lesson_id':d['id'],'deployed':False}

def online(a):
    _,m=verify_local(a.lesson);require(a.base_url.startswith('https://'),'HTTPS URL required');results=[]
    for f in m['files']+[{'path':'lesson-manifest.json','sha256':sha(Path(a.lesson)/'lesson-manifest.json')}]:
        from urllib.parse import quote
        url=a.base_url.rstrip('/')+'/'+quote(f['path'])
        with urllib.request.urlopen(url,timeout=60) as r:
            require(r.status==200,'HTTP failure');h=hashlib.sha256()
            while True:
                chunk=r.read(1024*1024)
                if not chunk:break
                h.update(chunk)
        require(h.hexdigest()==f['sha256'],'online hash differs: '+f['path']);results.append(f['path'])
    return {'online_verified':True,'files':results,'browser_verified':False}

def main():
    p=argparse.ArgumentParser();subs=p.add_subparsers(dest='command',required=True)
    v=subs.add_parser('validate');v.add_argument('--input',required=True)
    b=subs.add_parser('build');b.add_argument('--input',required=True);b.add_argument('--out',required=True);b.add_argument('--media');b.add_argument('--poster')
    i=subs.add_parser('integrate');i.add_argument('--html',required=True);i.add_argument('--lesson',required=True);i.add_argument('--backup-dir',required=True);i.add_argument('--apply',action='store_true')
    o=subs.add_parser('verify-online');o.add_argument('--lesson',required=True);o.add_argument('--base-url',required=True)
    a=p.parse_args()
    try:
        result={'validated':True,'chapters':len(validate(read(a.input))['chapters'])} if a.command=='validate' else {'build':build,'integrate':integrate,'verify-online':online}[a.command](a)
        print(dump(result))
    except (ValueError,OSError,KeyError,TypeError) as e:p.exit(1,str(e)+'\n')
if __name__=='__main__':main()
