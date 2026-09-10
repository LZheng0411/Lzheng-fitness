"""Source selection/resume boundaries without accessing anyone's real collection."""
import contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/lzheng-video-learning/scripts'))
import video_learning as v

class LearningTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.runtime=v.paths(NS(workspace=str(self.root)))
  self.ids=['123456789','123456790','123456791','123456792']
  self.selection=self.root/'selection.json';self.selection.write_text(json.dumps(self.ids))
  v.select(NS(input=self.selection,question='学习摄影曝光'),self.runtime)
 def tearDown(self):self.tmp.cleanup()
 def fake(self,kind,identifier):
  p=self.runtime/(identifier+'-'+kind+'.json');p.write_text(json.dumps({'source_id':'douyin:'+identifier}));return p
 def test_any_topic_and_more_than_three(self):
  self.assertEqual(v.state(self.runtime)['selection'],self.ids)
  self.assertEqual(v.state(self.runtime)['question'],'学习摄影曝光')
 def test_resume_deduplicates_and_new_question_prepares_again(self):
  async def capture(a):return self.fake('metadata',a.id)
  def down(a):return self.fake('media',Path(a.metadata).name.split('-')[0])
  def trans(a):return self.fake('transcript',a.id)
  def prep(a):return self.fake('packet',a.id)
  with patch.object(v.source,'capture',side_effect=capture) as c,patch.object(v.source,'download',side_effect=down) as d,patch.object(v.source,'transcribe',side_effect=trans) as t,patch.object(v.source,'prepare',side_effect=prep) as p:
   args=NS(limit=2,model='small',retry_failed=False);v.batch(args,self.runtime);v.batch(args,self.runtime);v.batch(args,self.runtime)
   self.assertEqual(c.call_count,4);self.assertEqual(t.call_count,4);self.assertEqual(p.call_count,4)
   v.select(NS(input=self.selection,question='比较摄影与绘画的构图'),self.runtime);v.batch(args,self.runtime)
   self.assertEqual(c.call_count,4);self.assertEqual(t.call_count,4);self.assertEqual(p.call_count,6)
 def test_failure_not_retried_without_flag_and_no_false_mastery(self):
  with patch.object(v.source,'capture',side_effect=RuntimeError('failed')) as c:
   a=NS(limit=4,model='small',retry_failed=False);v.batch(a,self.runtime);v.batch(a,self.runtime);self.assertEqual(c.call_count,4)
   a.retry_failed=True;v.batch(a,self.runtime);self.assertEqual(c.call_count,8)
  self.assertTrue(all(e['status']=='failed' for e in v.state(self.runtime)['works'].values()))
 def test_lock_refuses_concurrent_operations(self):
  with v.lock(self.runtime):
   with self.assertRaises(ValueError):
    with v.lock(self.runtime):pass
 def test_workspace_cannot_be_installed_skill(self):
  with self.assertRaises(ValueError):v.paths(NS(workspace=str(Path(v.__file__).resolve().parents[1])))

 def test_unavailable_address_refreshes_once_and_resumes_without_duplicates(self):
  async def capture(a):return self.fake('metadata-'+str(c.call_count),a.id)
  def down(a):
   if d.call_count==1:raise HTTPError('https://www.douyin.com/redacted',403,'Forbidden',None,None)
   return self.fake('media',self.ids[0])
  with patch.object(v.source,'capture',side_effect=capture) as c,patch.object(v.source,'download',side_effect=down) as d,patch.object(v.source,'transcribe',side_effect=lambda a:self.fake('transcript',a.id)) as t,patch.object(v.source,'prepare',side_effect=lambda a:self.fake('packet',a.id)) as p:
   args=NS(limit=1,model='small',retry_failed=False);v.batch(args,self.runtime)
   entry=v.state(self.runtime)['works'][self.ids[0]]
   self.assertEqual(entry['status'],'source_ready');self.assertEqual(c.call_count,2);self.assertEqual(d.call_count,2)
   self.assertIn('metadata-2',entry['metadata']['path'])
   self.selection.write_text(json.dumps([self.ids[0]]));v.select(NS(input=self.selection,question='学习摄影曝光'),self.runtime)
   v.batch(args,self.runtime)
   self.assertEqual((c.call_count,d.call_count,t.call_count,p.call_count),(2,2,1,1))

 def test_persistent_failure_is_bounded_and_drops_unusable_metadata(self):
  async def capture(a):return self.fake('metadata-'+str(c.call_count),a.id)
  error=HTTPError('https://www.douyin.com/redacted?token=do-not-log',403,'Forbidden',None,None)
  with patch.object(v.source,'capture',side_effect=capture) as c,patch.object(v.source,'download',side_effect=error) as d:
   args=NS(limit=1,model='small',retry_failed=False);v.batch(args,self.runtime)
   entry=v.state(self.runtime)['works'][self.ids[0]]
   self.assertEqual(entry['status'],'failed');self.assertNotIn('metadata',entry)
   self.assertEqual((c.call_count,d.call_count),(2,2));self.assertNotIn('token',entry['error'])
   args.retry_failed=True;v.batch(args,self.runtime)
   self.assertEqual((c.call_count,d.call_count),(4,4))

 def test_failed_recapture_can_recover_on_next_explicit_retry(self):
  async def capture(a):
   if c.call_count==2:raise RuntimeError('login required')
   return self.fake('metadata-'+str(c.call_count),a.id)
  def down(a):
   if d.call_count==1:raise v.source.MediaAddressUnavailable('no playable address')
   return self.fake('media',self.ids[0])
  with patch.object(v.source,'capture',side_effect=capture) as c,patch.object(v.source,'download',side_effect=down) as d,patch.object(v.source,'transcribe',side_effect=lambda a:self.fake('transcript',a.id)),patch.object(v.source,'prepare',side_effect=lambda a:self.fake('packet',a.id)):
   args=NS(limit=1,model='small',retry_failed=False);v.batch(args,self.runtime)
   self.assertNotIn('metadata',v.state(self.runtime)['works'][self.ids[0]])
   args.retry_failed=True;v.batch(args,self.runtime)
   self.assertEqual(v.state(self.runtime)['works'][self.ids[0]]['status'],'source_ready')
   self.assertEqual((c.call_count,d.call_count),(3,2))

 def test_manual_capture_replaces_failed_batch_metadata(self):
  identifier=self.ids[0];old=self.fake('old',identifier);s=v.state(self.runtime)
  entry=s['works'][identifier];v.remember(entry,'metadata',old);entry['status']='failed';v.base.save(self.runtime/'learning-state.json',s)
  fresh=self.fake('new',identifier)
  async def capture(a):return fresh
  def down(a):
   self.assertEqual(Path(a.metadata),fresh);return self.fake('media',identifier)
  with patch.object(v.source,'capture',side_effect=capture) as c,patch.object(v.source,'download',side_effect=down) as d,patch.object(v.source,'transcribe',side_effect=lambda a:self.fake('transcript',a.id)),patch.object(v.source,'prepare',side_effect=lambda a:self.fake('packet',a.id)):
   v.capture_selected(NS(id=identifier),self.runtime)
   v.batch(NS(limit=1,model='small',retry_failed=True),self.runtime)
   self.assertEqual((c.call_count,d.call_count),(1,1));self.assertEqual(v.state(self.runtime)['works'][identifier]['status'],'source_ready')

 def test_manual_capture_keeps_verified_media_and_transcript(self):
  identifier=self.ids[0];s=v.state(self.runtime);entry=s['works'][identifier]
  for kind in ('metadata','media','transcript','packet'):v.remember(entry,kind,self.fake(kind,identifier))
  entry.update(status='source_ready',model='small');v.base.save(self.runtime/'learning-state.json',s)
  async def capture(a):return self.fake('refreshed',identifier)
  with patch.object(v.source,'capture',side_effect=capture),patch.object(v.source,'download') as d,patch.object(v.source,'transcribe') as t,patch.object(v.source,'prepare',side_effect=lambda a:self.fake('new-packet',a.id)) as p:
   v.capture_selected(NS(id=identifier),self.runtime)
   v.batch(NS(limit=1,model='small',retry_failed=False),self.runtime)
   d.assert_not_called();t.assert_not_called();self.assertEqual(p.call_count,1)

 def test_unrelated_failures_do_not_refresh_addresses(self):
  for error in (PermissionError('disk'),TimeoutError('network'),ValueError('unsupported redirect'),HTTPError('https://www.douyin.com/redacted',429,'Rate limited',None,None)):
   with self.subTest(error=type(error).__name__):
    async def capture(a):return self.fake('metadata',a.id)
    with patch.object(v.source,'capture',side_effect=capture) as c,patch.object(v.source,'download',side_effect=error) as d:
     v.batch(NS(limit=1,model='small',retry_failed=True),self.runtime)
     self.assertLessEqual(c.call_count,1);self.assertEqual(d.call_count,1)

 def test_transcription_retry_reuses_downloaded_media(self):
  async def capture(a):return self.fake('metadata',a.id)
  def trans(a):
   if t.call_count==1:raise RuntimeError('model unavailable')
   return self.fake('transcript',a.id)
  with patch.object(v.source,'capture',side_effect=capture) as c,patch.object(v.source,'download',side_effect=lambda a:self.fake('media',self.ids[0])) as d,patch.object(v.source,'transcribe',side_effect=trans) as t,patch.object(v.source,'prepare',side_effect=lambda a:self.fake('packet',a.id)):
   args=NS(limit=1,model='small',retry_failed=False);v.batch(args,self.runtime)
   args.retry_failed=True;v.batch(args,self.runtime)
   self.assertEqual((c.call_count,d.call_count,t.call_count),(1,1,2));self.assertEqual(v.state(self.runtime)['works'][self.ids[0]]['status'],'source_ready')

if __name__=='__main__':unittest.main()
