#!/usr/bin/env python3
"""Inspect and update known Relay MCP v2 Railway deployments. Python 3.9+."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.parse
import uuid

ROOT = Path(__file__).resolve().parents[1]
SESSION = 'relay-mcp-updater-' + uuid.uuid4().hex[:12]

class UpdateError(Exception):
    pass

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def run(args, cwd=None, timeout=120):
    env = dict(os.environ, RAILWAY_CALLER='skill:relay-mcp-updater@1.0.0', RAILWAY_AGENT_SESSION=SESSION)
    try:
        p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise UpdateError(f'{args[0]} did not finish. Inspect state before retrying; do not repeat an uncertain deployment.') from e
    if p.returncode:
        # Do not echo subprocess output: variable/build commands can contain secrets.
        raise UpdateError(f'{args[0]} {args[1]} failed (exit {p.returncode}). Inspect locally; output withheld to protect credentials.')
    return p.stdout

def railway(args, cwd=None):
    return json.loads(run(['railway', *args, '--json'], cwd))

def unique(items, value, label):
    matches = [x for x in items if value in (x.get('id'), x.get('name'))]
    if len(matches) != 1:
        raise UpdateError(f'{label} must match exactly one name or ID; found {len(matches)}. Specify an explicit ID.')
    return matches[0]

def nodes(edges):
    return [x['node'] for x in edges.get('edges', [])]

def select_target(projects, project, environment, service):
    p = unique(projects, project, 'Project')
    e = unique(nodes(p['environments']), environment, 'Environment')
    services = nodes(p['services'])
    s = unique(services, service, 'Service') if service else (services[0] if len(services) == 1 else None)
    if s is None:
        raise UpdateError('Multiple services found. Specify --service; no default service will be deployed.')
    return {'project':p['id'], 'environment':e['id'], 'service':s['id'], 'name':s['name']}

def inspect_source(source, manifest):
    source = Path(source).resolve()
    problems = []
    for rel, rule in manifest['files'].items():
        p = source / rel
        if p.is_symlink() or (p.exists() and not p.is_file()):
            problems.append(rel + ': unsupported file type'); continue
        if not p.exists():
            if not rule['optional_before']: problems.append(rel + ': missing')
        elif digest(p) not in rule['accepted_sha256']:
            problems.append(rel + ': customized or unsupported revision')
    if (source/'src').exists():
        for p in (source/'src').rglob('*'):
            if p.is_file() and str(p.relative_to(source)) not in manifest['files']:
                problems.append(str(p.relative_to(source)) + ': unrecognized source file')
    if problems: raise UpdateError('Automatic patch refused; preserve custom changes:\n'+'\n'.join(problems))
    return source

def find_source(project, service, manifest):
    config = Path.home()/'.railway/config.json'
    if not config.exists(): raise UpdateError('Source checkout required: pass --source /path/to/relay-mcp-server.')
    entries = json.loads(config.read_text()).get('projects', {})
    candidates = []
    for location, linked in entries.items():
        if linked.get('project') == project and linked.get('service') == service:
            p = Path(location)
            if (p/'src/auth/provider.ts').is_file(): candidates.append(p)
    if not candidates: raise UpdateError('No linked source checkout found. Pass --source; do not substitute a fresh template for an unknown deployed server.')
    # Multiple equivalent copies are safe; different copies require the owner to select.
    fingerprints = {tuple((rel, digest(p/rel) if (p/rel).is_file() else None) for rel in manifest['files']) for p in candidates}
    if len(fingerprints) != 1: raise UpdateError('Multiple different source checkouts found. Specify --source.')
    return inspect_source(candidates[0], manifest)

def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'relay-mcp-updater/1.0'}),timeout=20) as r:
        return json.load(r)

def valid_url(url):
    p = urllib.parse.urlsplit(url)
    if p.scheme != 'https' or not p.netloc or p.username or p.password or p.query or p.fragment:
        raise UpdateError('Expected an HTTPS base URL without embedded credentials, query, or fragment.')
    return url.rstrip('/')

def auth_summary(data):
    providers = data.get('oauth2',{}).get('providers',data.get('authProviders',[]))
    return {'password_enabled':data.get('password',{}).get('enabled'),
            'oauth_enabled':data.get('oauth2',{}).get('enabled',bool(providers)),
            'providers':[p['name'] for p in providers]}

def stage_release(source, destination, manifest):
    """Copy only validated bundled deployment files; never upload .env or local data."""
    inspect_source(source, manifest)
    for rel, rule in manifest['files'].items():
        if digest(ROOT/'assets/server'/rel) != rule['sha256']:
            raise UpdateError('Bundled file checksum mismatch: '+rel)
    destination.mkdir(parents=True)
    for rel in manifest['files']:
        dest = destination / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/'assets/server'/rel, dest)
    (destination/'.railwayignore').write_text('node_modules/\ndist/\n.git/\n.env\n.env.*\ntests/\n')
    (destination/'.dockerignore').write_text('node_modules\ndist\n.git\n.env\n.env.*\ntests\n')
    return destination

def deployed_matches(public_url, manifest):
    try:
        health = get_json(public_url+'/health')
        if health.get('version') != manifest['server_version'] or health.get('build') != manifest.get('runtime_sha256'): return False
        if not manifest.get('runtime_sha256'): return False
        for name in ['relay-login.js','auth-methods.js']:
            with urllib.request.urlopen(public_url+'/assets/'+name,timeout=20) as r:
                sha=hashlib.sha256(r.read()).hexdigest()
            if sha != manifest['files']['src/public/'+name]['sha256']: return False
        return True
    except Exception:
        return False

def rollback_target(instance):
    healthy = [d for d in instance.get('activeDeployments', []) if d.get('status') == 'SUCCESS']
    return healthy[0]['id'] if len(healthy) == 1 else None

def compare_deployed(source, remote):
    for rel, sha in remote.items():
        p = Path(source)/rel
        if not p.is_file() or digest(p) != sha:
            raise UpdateError('Local checkout does not match deployed source: '+rel)

def verify_deployed_source(source, target, manifest):
    prefix = ['railway','ssh','-p',target['project'],'-e',target['environment'],'-s',target['service'],'--']
    try:
        paths=run(prefix+['find','/app/src','-type','f']).splitlines()
        if not paths or any(not p.startswith('/app/src/') for p in paths):
            raise UpdateError('Unexpected deployed source layout')
        rels=[p[len('/app/'):] for p in paths]
        rels += ['package.json','package-lock.json','tsconfig.json']
        if any(r not in manifest['files'] for r in rels):
            raise UpdateError('Deployed source includes custom or unsupported files')
        lines=run(prefix+['sha256sum',*['/app/'+r for r in rels]]).splitlines()
        remote={}
        for line in lines:
            sha, name=line.split(None,1);name=name.strip()
            if len(sha)!=64 or not name.startswith('/app/'):
                raise UpdateError('Unexpected fingerprint response')
            remote[name[len('/app/'):]]=sha
        if set(remote)!=set(rels):raise UpdateError('Incomplete deployed fingerprints')
        compare_deployed(source,remote)
        for r in manifest['files']:
            if r.startswith('src/') and (Path(source)/r).is_file() and r not in remote:
                raise UpdateError('Local checkout is newer than deployed source: '+r)
    except UpdateError as e:
        raise UpdateError('Cannot verify actual deployed source. Configure Railway SSH access in your account or inspect/merge manually. '+str(e)) from e

def status_instance(status, target):
    e = unique(nodes(status['environments']),target['environment'],'Environment')
    found=[x for x in nodes(e.get('serviceInstances',{})) if x['serviceId']==target['service']]
    if len(found)!=1: raise UpdateError('Target service instance not uniquely resolved.')
    return found[0]

def save_report(path, report):
    path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    os.chmod(path,0o600)

def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--project',required=True,help='Exact Railway project name or ID')
    a.add_argument('--environment',default='production')
    a.add_argument('--service',help='Required when the project has multiple services')
    a.add_argument('--source',type=Path,help='Existing deployed-source checkout; auto-discovered from Railway links if omitted')
    a.add_argument('--apply',action='store_true',help='Authorize validated deployment. Default is read-only diagnosis.')
    a.add_argument('--work-dir',type=Path,default=Path.cwd()/'work/relay-mcp-updates')
    args=a.parse_args()
    manifest=json.loads((ROOT/'manifest.json').read_text())
    target=select_target(railway(['list']),args.project,args.environment,args.service)
    work=args.work_dir.resolve()/SESSION;work.mkdir(parents=True,mode=0o700)
    report={'release':manifest['release'],'target':target,'result':'inspecting','authenticated_mcp_check':'requires_user_login'}
    report_path=work/'report.json'
    try:
        # Local scratch link only. Never change the user's existing checkout link.
        run(['railway','link','--project',target['project'],'--environment',target['environment'],'--service',target['service']],work)
        instance=status_instance(railway(['status'],work),target)
        previous=(instance.get('latestDeployment') or {}).get('id')
        report['previous_deployment']=rollback_target(instance)
        report['observed_latest_deployment']=previous
        values=railway(['variables'],work)
        pub=valid_url(values.get('PUBLIC_URL',''))
        pb=valid_url(values.get('PB_AUTH_URL',''))
        collection=values.get('PB_COLLECTION','users')
        # Match configured public URL to Railway's own domain inventory.
        domains=instance.get('domains',{})
        allowed=[x['domain'] for k in ['serviceDomains','customDomains'] for x in domains.get(k,[])]
        if urllib.parse.urlsplit(pub).hostname not in allowed:
            raise UpdateError('PUBLIC_URL does not match this Railway service domain; repair configuration first.')
        report['public_url']=pub
        report['auth']=auth_summary(get_json(pb+'/api/collections/'+urllib.parse.quote(collection,safe='')+'/auth-methods'))
        if not report['auth']['oauth_enabled'] or not report['auth']['providers']:
            raise UpdateError('No OAuth providers available. This social-login repair is not applicable.')
        if deployed_matches(pub,manifest):
            report['result']='already_current';save_report(report_path,report)
            print(json.dumps(report,ensure_ascii=False,indent=2));print('Report:',report_path);return
        source=inspect_source(args.source,manifest) if args.source else find_source(target['project'],target['service'],manifest)
        if args.apply:
            verify_deployed_source(source,target,manifest)
            report['source_provenance']='matched_running_service_via_ssh'
        else:
            report['source_provenance']='not_verified_dry_run_only'
        stage=stage_release(source,work/'staged-server',manifest)
        # Backup only known source files; credential files and volume data are never copied.
        backup=work/'source-backup';backup.mkdir()
        for rel in manifest['files']:
            old=source/rel
            if old.is_file():
                dest=backup/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,dest)
        report['source_backup']=str(backup);report['staged_source']=str(stage)
        report['result']='compatible_dry_run';save_report(report_path,report)
        if not args.apply:
            print(json.dumps(report,ensure_ascii=False,indent=2));print('Run with --apply to build and deploy. Report:',report_path);return
        # Do not run dependency installation scripts. Build/test only after compatibility verification.
        run(['npm','ci','--ignore-scripts','--no-audit','--no-fund'],stage,300)
        run(['npm','test'],stage,120)
        # Refuse deployment if another operator deployed since our diagnosis.
        current=status_instance(railway(['status'],work),target)
        if (current.get('latestDeployment') or {}).get('id') != previous:
            raise UpdateError('Deployment changed during preparation. Inspect the new version before retrying.')
        report['result']='upload_started';save_report(report_path,report)
        message=f'Relay OAuth repair {manifest["release"]} {SESSION}'
        run(['railway','up','--project',target['project'],'--environment',target['environment'],'--service',target['service'],'--detach','-m',message],stage,300)
        deadline=time.monotonic()+300;deployment=None
        while time.monotonic()<deadline:
            releases=railway(['deployment','list','--limit','8'],work)
            matches=[d for d in releases if d.get('meta',{}).get('cliMessage')==message]
            if len(matches)==1:deployment=matches[0]
            if deployment:
                report['deployment']=deployment['id'];report['deployment_status']=deployment['status'];save_report(report_path,report)
                if deployment['status']=='SUCCESS':break
                if deployment['status'] in ['FAILED','CRASHED','REMOVED']:
                    raise UpdateError('Deployment failed. Inspect the recorded deployment; restore previous deployment in Railway if needed. Do not repeat upload.')
            print('Waiting for this deployment to finish...',flush=True);time.sleep(10)
        if not deployment or deployment['status']!='SUCCESS':
            raise UpdateError('Deployment result not confirmed within 5 minutes. Inspect recorded state; do not automatically re-upload.')
        if not deployed_matches(pub,manifest):raise UpdateError('New deployment succeeded but public health/assets do not match. Inspect routing or rollback.')
        # Variables are never mutated. Compare in memory and emit no values.
        if railway(['variables'],work)!=values:
            report['variables_check']='changed_during_run_review_required'
        else: report['variables_check']='unchanged'
        report['result']='deployed_health_verified'
        save_report(report_path,report)
        print(json.dumps(report,ensure_ascii=False,indent=2));print('Report:',report_path)
        print('Restart the MCP connector, sign in, then verify initialize + vault_relays + vault_folders. Health is not proof of login.')
    except Exception as e:
        report['result']='needs_attention';report['error']=str(e);save_report(report_path,report)
        raise UpdateError(f'{e}\nSaved report: {report_path}') from e

if __name__=='__main__':
    try:main()
    except (UpdateError,ValueError,KeyError) as e:print(str(e),file=sys.stderr);sys.exit(1)
