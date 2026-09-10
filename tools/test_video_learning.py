"""Source selection/resume boundaries without accessing anyone's real collection."""
import contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
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

if __name__=='__main__':unittest.main()
