import importlib.util,json,tempfile,unittest,shutil
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];SKILL=ROOT/'skills/relay-mcp-updater'
spec=importlib.util.spec_from_file_location('updater',SKILL/'scripts/update.py');u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
class UpdaterTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.source=self.root/'server';shutil.copytree(SKILL/'assets/server',self.source,ignore=shutil.ignore_patterns('node_modules','dist'));self.manifest=json.loads((SKILL/'manifest.json').read_text())
 def test_current_source_accepted(self):self.assertEqual(u.inspect_source(self.source,self.manifest),self.source.resolve())
 def test_customized_auth_is_preserved(self):
  p=self.source/'src/auth/provider.ts';p.write_text(p.read_text()+'\n// customer behavior\n')
  with self.assertRaisesRegex(u.UpdateError,'customized'):u.stage_release(self.source,self.root/'stage',self.manifest)
  self.assertFalse((self.root/'stage').exists());self.assertIn('customer behavior',p.read_text())
 def test_extra_source_refused(self):
  (self.source/'src/customer.ts').write_text('export const custom=true;')
  with self.assertRaisesRegex(u.UpdateError,'unrecognized'):u.inspect_source(self.source,self.manifest)
 def test_missing_source_refused(self):
  (self.source/'src/config.ts').unlink()
  with self.assertRaisesRegex(u.UpdateError,'missing'):u.inspect_source(self.source,self.manifest)
 def test_secrets_never_enter_stage(self):
  (self.source/'.env').write_text('PRIVATE_SECRET=do-not-upload');(self.source/'notes.md').write_text('private notes')
  stage=u.stage_release(self.source,self.root/'stage',self.manifest)
  self.assertFalse((stage/'.env').exists());self.assertFalse((stage/'notes.md').exists());self.assertTrue((stage/'src/index.ts').exists())
 def test_payload_tamper_refused(self):
  self.manifest['files']['src/index.ts']['sha256']='0'*64
  with self.assertRaisesRegex(u.UpdateError,'checksum'):u.stage_release(self.source,self.root/'stage',self.manifest)
  self.assertFalse((self.root/'stage').exists())
 def test_ambiguous_project_refused(self):
  with self.assertRaisesRegex(u.UpdateError,'exactly one'):u.unique([{'id':'a','name':'same'},{'id':'b','name':'same'}],'same','Project')
 def test_custom_service_name(self):
  projects=[{'id':'p','name':'customer','environments':{'edges':[{'node':{'id':'e','name':'staging'}}]},'services':{'edges':[{'node':{'id':'s','name':'custom-relay'}}]}}]
  self.assertEqual(u.select_target(projects,'customer','staging','custom-relay')['service'],'s')
 def test_multiple_services_refused(self):
  projects=[{'id':'p','name':'project','environments':{'edges':[{'node':{'id':'e','name':'production'}}]},'services':{'edges':[{'node':{'id':'s1','name':'one'}},{'node':{'id':'s2','name':'two'}}]}}]
  with self.assertRaisesRegex(u.UpdateError,'Multiple services'):u.select_target(projects,'p','e',None)
 def test_legacy_password_flag_not_authoritative(self):
  summary=u.auth_summary({'emailPassword':True,'password':{'enabled':False},'authProviders':[{'name':'google'}]})
  self.assertFalse(summary['password_enabled']);self.assertEqual(summary['providers'],['google'])
 def test_modern_disabled_respected(self):self.assertFalse(u.auth_summary({'oauth2':{'enabled':False,'providers':[]},'authProviders':[{'name':'google'}]})['oauth_enabled'])
 def test_url_credentials_refused(self):
  with self.assertRaises(u.UpdateError):u.valid_url('https://user:secret@example.com')
 def test_health_alone_not_success(self):
  with patch.object(u,'get_json',return_value={'version':self.manifest['server_version']}),patch.object(u.urllib.request,'urlopen',side_effect=OSError('missing assets')):
   self.assertFalse(u.deployed_matches('https://example.com',self.manifest))
if __name__=='__main__':unittest.main()

class DeploymentSafetyTests(unittest.TestCase):
 def test_bundle_extras_are_not_copied(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);skill=root/'skill';shutil.copytree(SKILL,skill,ignore=shutil.ignore_patterns('node_modules','dist','__pycache__'))
   (skill/'assets/server/session-private.json').write_text('secret')
   m=json.loads((skill/'manifest.json').read_text())
   with patch.object(u,'ROOT',skill):stage=u.stage_release(skill/'assets/server',root/'staged',m)
   self.assertFalse((stage/'session-private.json').exists())
 def test_latest_failed_is_not_rollback_target(self):
  instance={'latestDeployment':{'id':'failed','status':'FAILED'},'activeDeployments':[{'id':'serving','status':'SUCCESS'}]}
  self.assertEqual(u.rollback_target(instance),'serving')
 def test_health_requires_backend_identity(self):
  m={'server_version':'2.0.1','runtime_sha256':'expected'}
  with patch.object(u,'get_json',return_value={'version':'2.0.1','build':'other'}):self.assertFalse(u.deployed_matches('https://example.com',m))
 def test_source_must_match_running_files(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'a.ts').write_text('local')
   with self.assertRaisesRegex(u.UpdateError,'deployed source'):u.compare_deployed(p,{'a.ts':'0'*64})
