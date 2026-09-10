"""Test independent knowledge writes, method-bound menus and third-party installation."""
import hashlib,importlib.util,json,os,re,subprocess,sys,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class Outputs(unittest.TestCase):
 def test_knowledge_writer_preserves_training_and_shell(self):
  with tempfile.TemporaryDirectory() as raw:
   root=Path(raw);project=root/'user';project.mkdir();page=project/'健身工作台.html';sample=R/'skills/lzheng-knowledge-library/assets/example-knowledge.json';script=R/'skills/lzheng-knowledge-library/scripts/publish_knowledge.py'
   original='<html><script id="workbench-data" type="application/json">{"private":"unchanged"}</script><script id="knowledge-library-data" type="application/json">[]</script></html>'
   page.write_text(original,encoding='utf-8')
   result=subprocess.run([sys.executable,str(script),'--html',str(page),'--data',str(sample),'--backup-dir',str(root/'backups'),'--apply'],capture_output=True)
   self.assertEqual(result.returncode,0,result.stderr.decode())
   pattern=re.compile(r'(<script id="knowledge-library-data" type="application/json">).*?(</script>)',re.S)
   self.assertEqual(pattern.sub('',page.read_text(encoding='utf-8')),pattern.sub('',original))
   broken=root/'broken.json';rows=json.loads(sample.read_text(encoding='utf-8'));rows.append(rows[0]);broken.write_text(json.dumps(rows))
   before=page.read_bytes();result=subprocess.run([sys.executable,str(script),'--html',str(page),'--data',str(broken),'--backup-dir',str(root/'backups'),'--apply'],capture_output=True)
   self.assertNotEqual(result.returncode,0);self.assertEqual(page.read_bytes(),before)
 def test_menu_method_version_and_unknown_nutrition(self):
  m=module('planner',R/'skills/lzheng-nutrition-system/scripts/update_planner.py')
  value={'schema':1,'current_plan':{'version':'menu-1','target_version':'target-1','target':{'version':'target-1','method':'user-selected-method'},'meals':[{'name':'早餐','foods':[{'name':'示例食物','portion':'用户待校准份量','macros':{'calories':None}}]}]}}
  m.validate(value);value['current_plan']['target']['version']='target-2'
  with self.assertRaises(ValueError):m.validate(value)
 def test_source_packet_must_match_video(self):
  sys.path.insert(0,str(R/'skills/lzheng-video-learning/scripts'));import question_tools as q
  with self.assertRaises(ValueError):q.validate({'source_id':'douyin:123456'}, {'source_id':'douyin:654321','segments':[{'start':0,'end':2,'text':'text'}]})
 def test_optional_learning_installs_license_and_never_overwrites(self):
  with tempfile.TemporaryDirectory() as raw:
   cmd=[sys.executable,str(R/'tools/install_learning.py'),'--dbs-learning','--agent-root',raw]
   run=subprocess.run(cmd,capture_output=True);self.assertEqual(run.returncode,0,run.stderr.decode())
   p=Path(raw)/'skills/dbs-learning';self.assertIn('NonCommercial',(p/'LICENSE').read_text())
   before=(p/'SKILL.md').read_bytes();again=subprocess.run(cmd,capture_output=True);self.assertNotEqual(again.returncode,0);self.assertEqual((p/'SKILL.md').read_bytes(),before)
 def test_public_example_has_sources_and_no_personal_identifiers(self):
  rows=json.loads((R/'skills/lzheng-knowledge-library/assets/example-knowledge.json').read_text(encoding='utf-8'))
  self.assertEqual(len(rows),6)
  text=json.dumps(rows,ensure_ascii=False)
  for blocked in ['66kg','P140','C260','v05','tcloudbaseapp','owner_id','accessKey'] :self.assertNotIn(blocked,text)
  self.assertTrue(all(r['sources'] and r['example'] for r in rows))
if __name__=='__main__':unittest.main()
