#!/usr/bin/env python3
"""After npm run build, check distribution source/runtime hashes; --write records an intentional release."""
from pathlib import Path
import hashlib,json,sys
root=Path(__file__).resolve().parents[1];server=root/'assets/server';m=json.loads((root/'manifest.json').read_text())
paths=sorted([p.relative_to(server) for folder in ['dist','src/public'] for p in (server/folder).rglob('*.js')]+[Path('package-lock.json')],key=str)
if not (server/'dist/index.js').exists():raise SystemExit('Run npm run build first')
h=hashlib.sha256()
for r in paths:h.update((str(r)+'\0').encode());h.update((server/r).read_bytes());h.update(b'\0')
errors=[]
for r,rule in m['files'].items():
 sha=hashlib.sha256((server/r).read_bytes()).hexdigest()
 if '--write' in sys.argv:rule['sha256']=sha;rule['accepted_sha256']=sorted(set(rule['accepted_sha256']+[sha]))
 elif sha!=rule['sha256']:errors.append(r)
if '--write' in sys.argv:
 m['runtime_sha256']=h.hexdigest();(root/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
elif m.get('runtime_sha256')!=h.hexdigest():errors.append('runtime fingerprint')
if errors:raise SystemExit('Manifest mismatch: '+', '.join(errors))
print('Bundle source and executable fingerprints verified')
