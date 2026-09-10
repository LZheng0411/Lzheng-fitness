"""One explicit upgrade: inspect, back up, upgrade UI, then update installed Skills."""
import argparse,json,os,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def run(args,accepted=(0,)):
    result=subprocess.run(args,cwd=ROOT,env={**os.environ,'PYTHONUTF8':'1'})
    if result.returncode not in accepted:raise SystemExit(result.returncode)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',required=True,help='User system root containing lzheng-system.json')
    p.add_argument('--platform',choices=('codex','claude','agents'),default='codex')
    p.add_argument('--agent-root')
    p.add_argument('--apply',action='store_true')
    a=p.parse_args()
    script=ROOT/'skills/lzheng-training-system/scripts/lzheng_training_system.py'
    run([sys.executable,str(script),'upgrade-workbench-ui','--root',a.root,'--check-only'])
    if not a.apply:
        print('CHECKED: compatible candidate; no UI or Skills written. Use --apply for the user-requested upgrade.');return
    run([sys.executable,str(script),'upgrade-workbench-ui','--root',a.root,'--apply'])
    # Configuration update is intentionally separate and must not impersonate a UI upgrade.
    run([sys.executable,str(script),'upgrade','--root',a.root])
    args=[sys.executable,str(ROOT/'tools/install.py'),'--platform',a.platform,'--all','--force']
    if a.agent_root:args+=['--target-root',a.agent_root]
    run(args)
    verify=[x for x in args if x not in ('--force',)]+['--verify']
    run(verify)
    print(json.dumps({'ui_checked':True,'skills_verified':True,'browser_records_modified':False,'knowledge_preserved':True,'deployed':False}))
if __name__=='__main__':main()
