#!/usr/bin/env python3
"""Resolve latest official release on every invocation, then run its updater."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.request

REPOSITORY = 'Monkkim/relay-mcp-updater'
ROOT = Path(__file__).resolve().parents[1]

def main():
    args=sys.argv[1:]
    if '--offline' in args:
        args.remove('--offline')
        return subprocess.call([sys.executable,str(ROOT/'scripts/update.py'),*args])
    if '--help' in args or '-h' in args:
        print('Checks the latest GitHub release each run. --offline uses installed files.\n')
        return subprocess.call([sys.executable,str(ROOT/'scripts/update.py'),'--help'])
    headers={'Accept':'application/vnd.github+json','User-Agent':'relay-mcp-updater'}
    # Optional environment token for private forks/API rate limits. Never saved or printed.
    if os.environ.get('GITHUB_TOKEN'):headers['Authorization']='Bearer '+os.environ['GITHUB_TOKEN']
    req=urllib.request.Request('https://api.github.com/repos/'+REPOSITORY+'/releases/latest',headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=20) as r: release=json.load(r)
        tag=release['tag_name']
        if not re.fullmatch(r'v\d+\.\d+\.\d+',tag) or release.get('draft') or release.get('prerelease'):
            raise RuntimeError('Expected a stable vX.Y.Z release.')
        with tempfile.TemporaryDirectory(prefix='relay-updater-release-') as folder:
            repo=Path(folder)/'release'
            # The source is fixed to the distribution owner; do not execute an arbitrary API URL.
            subprocess.run(['git','clone','--quiet','--depth','1','--branch',tag,
                            'https://github.com/'+REPOSITORY+'.git',str(repo)],check=True,timeout=120)
            skill=repo/'skills/relay-mcp-updater'
            manifest=json.loads((skill/'manifest.json').read_text())
            if manifest['release']!=tag:raise RuntimeError('Release tag and manifest do not match.')
            revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
            print('Using official release',tag,'commit',revision,flush=True)
            return subprocess.call([sys.executable,str(skill/'scripts/update.py'),*args])
    except Exception as e:
        print('Latest release could not be verified. No deployment started. Use --offline only if you intentionally want the installed version. '+str(e),file=sys.stderr)
        return 1

if __name__=='__main__':sys.exit(main())
