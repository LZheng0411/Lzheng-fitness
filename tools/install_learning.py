"""Explicit optional install; preserves the upstream noncommercial license."""
import argparse
from pathlib import Path
import install

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--platform',choices=('codex','claude','agents'),default='codex')
    p.add_argument('--agent-root',type=Path)
    p.add_argument('--dbs-learning',action='store_true',required=True)
    a=p.parse_args()
    root=a.agent_root or install.default_agent_root(a.platform)
    install.SOURCE_ROOT=Path(__file__).resolve().parents[1]/'third_party'
    install.install_skill('dbs-learning',root/'skills',False,None)
    print('Installed original dbs-learning with LICENSE and UPSTREAM.json. CC BY-NC 4.0; commercial use needs separate authorization. Existing installations are never overwritten.')
if __name__=='__main__':main()
