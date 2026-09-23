import copy, importlib.util, json, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];SKILL=ROOT/'skills/lzheng-video-lessons'
spec=importlib.util.spec_from_file_location('lesson',SKILL/'scripts/lesson.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class Lessons(unittest.TestCase):
 def setUp(self):self.data=mod.read(SKILL/'assets/example-lesson.json');self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def build(self):
  src=self.root/'source.json';src.write_text(json.dumps(self.data),encoding='utf-8');out=self.root/'lesson';mod.build(SimpleNamespace(input=src,out=out,media=None,poster=None));return out
 def test_bounds(self):
  for edit in [lambda d:d['chapters'][0].update(end=99),lambda d:d['chapters'][1].update(start=1),lambda d:d['chapters'][0]['details'][0].update(at=6),lambda d:d['chapters'][1].update(id=d['chapters'][0]['id']),lambda d:d['chapters'][0].update(verified=False)]:
   d=copy.deepcopy(self.data);edit(d)
   with self.assertRaises(ValueError):mod.validate(d)
 def test_rebuild_preserves_existing(self):
  folder=self.build();before=(folder/'index.html').read_bytes()
  with self.assertRaises(ValueError):self.build()
  self.assertEqual(before,(folder/'index.html').read_bytes())
 def test_integrate_and_update(self):
  folder=self.build();page=self.root/'workbench.html';training='<script id="workbench-data" type="application/json">{"keep":123}</script>'
  page.write_text('<html><body><section id="m-knowledge"></section>'+training+'</body></html>',encoding='utf-8');a=SimpleNamespace(html=page,lesson=folder,backup_dir=self.root/'backup',apply=False);before=page.read_bytes();mod.integrate(a);self.assertEqual(before,page.read_bytes());a.apply=True;mod.integrate(a);mod.integrate(a);s=page.read_text(encoding='utf-8');self.assertIn(training,s);self.assertEqual(s.count('id="portable-lessons-ui"'),1);self.assertEqual(s.count('"id": "sample-lesson"'),1)
 def test_tamper_and_path(self):
  folder=self.build();(folder/'chapters.js').write_text('tamper',encoding='utf-8')
  with self.assertRaises(ValueError):mod.verify_local(folder)
 def test_text_is_literal(self):
  self.data['title']='</script><script>alert(1)</script>';folder=self.build();s=(folder/'index.html').read_text(encoding='utf-8');self.assertNotIn(self.data['title'],s);self.assertIn('&lt;/script&gt;',s)
 def test_local_source(self):
  self.data['source_type']='local';self.data['source_url']='';folder=self.build();self.assertIn('用户提供的本地视频',(folder/'index.html').read_text(encoding='utf-8'))
 def test_encoded_path(self):
  folder=self.build();new=self.root/'course#1%';folder.rename(new);page=self.root/'workbench.html';page.write_text('<body><section id="m-knowledge"></section></body>',encoding='utf-8');mod.integrate(SimpleNamespace(html=page,lesson=new,backup_dir=self.root/'backup',apply=True));self.assertIn('course%231%25/index.html',page.read_text(encoding='utf-8'))
 def test_link_mode(self):
  folder=self.build();s=(folder/'index.html').read_text(encoding='utf-8');self.assertIn('仅原视频链接',s);self.assertNotIn('src="video.mp4"',s);self.assertNotIn('__MEDIA',s);mod.verify_local(folder)
if __name__=='__main__':unittest.main()
