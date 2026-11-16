"""Prepare/build the full official Wi-Fi C manifest with the explicit Peach layer.

Reference repositories and boot candidates are not changed. Generated removals
are redirected to a private macOS Trash bucket with a recovery journal.
"""
import argparse,gzip,hashlib,io,json,os,re,shutil,subprocess,sys,tarfile,uuid
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
COMPONENT='5f7f5a8a9f02f7ab45ed10a2f226e348c519a838'
BOARD='e8937177309d88c93b305a57bad147fd5fac8a86'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):p.write_text(json.dumps(value,indent=2)+'\n')
def git(repo,*args):return subprocess.check_output(['git','-c','core.autocrlf=false','-c','core.eol=lf','-C',str(repo),*args])
def main():
    if sys.flags.optimize:raise ValueError('Validation requires Python assertions enabled')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('component-repository','board-repository','linux-archive','supplicant-archive','backport','llvm','kernel-reference','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--native-lifecycle',action='store_true',help='Require real native consumer/BM callbacks')
    a=p.parse_args();out=a.output.resolve()
    if out.exists():raise ValueError('New output directory required')
    linux=json.loads((ROOT/'drivers/EldenWifi/peach/runtime-linux-input.json').read_text());raw=gzip.decompress(a.linux_archive.read_bytes())
    if hashlib.sha256(raw).hexdigest()!=linux['tar_sha256']:raise ValueError('Wrong full Linux snapshot')
    backport=json.loads((a.backport/'result.json').read_text())
    if backport['base_commit']!=linux['commit']:raise ValueError('Wrong Peach source base')
    out.mkdir(parents=True);module=out/'component';module.mkdir();objects=out/'objects';objects.mkdir()
    packed=git(a.component_repository,'archive',COMPONENT)
    with tarfile.open(fileobj=io.BytesIO(packed)) as t:t.extractall(module,filter='data')
    base=module/'deps/linux';base.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(raw)) as t:t.extractall(base,filter='data')
    lock=json.loads((module/'tools/source-lock.json').read_text())
    if lock['linux']['commit']!=linux['commit'] or sha(a.supplicant_archive)!=lock['supplicant']['sha256']:raise ValueError('Source lock differs')
    for name,info in backport['files'].items():
        target=base/name;data=(a.backport/'tree'/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=info['output_sha256']:raise ValueError('Peach source changed')
        if info['base_sha256']:
            if sha(target)!=info['base_sha256']:raise ValueError('Peach parent changed')
        elif target.exists():raise ValueError('New header already exists')
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    archive=module/'deps'/lock['supplicant']['archive'];shutil.copyfile(a.supplicant_archive,archive)
    with tarfile.open(archive) as t:t.extractall(module/'deps',filter='data')
    checked={str(base/name):sha(base/name) for name in set(lock['linux']['required'])|set(backport['files'])}
    for name in lock['supplicant']['required']:
        target=module/'deps'/lock['supplicant']['directory']/name;checked[str(target)]=sha(target)
    identity={'source_lock_sha256':sha(module/'tools/source-lock.json'),'sources':{
        'linux':{'revision':linux['commit'],'base_tar_sha256':linux['tar_sha256'],'explicit_peach_layer_sha256':sha(a.backport/'result.json')},
        'supplicant':{'archive_sha256':sha(archive)},'freebsd':{'consumed_by_this_build':False,'not_fetched':True}},'provided_snapshot':True}
    input_manifest=out/'provided-inputs.json';write(input_manifest,{'checked_files':checked,'identity':identity,'identity_output':str(module/'out/source-identity.json')})
    hooks=out/'hooks';hooks.mkdir();(hooks/'bin').mkdir()
    for name in ('generated_trash.py','wifi_snapshot_check.py'):shutil.copyfile(ROOT/'tools/build_support'/name,hooks/name)
    (hooks/'sitecustomize.py').write_text('from generated_trash import install\ninstall()\n')
    rm=hooks/'bin/rm';rm.write_text('#!'+sys.executable+'\nfrom generated_trash import shell_main\nshell_main()\n');rm.chmod(0o755)
    trash=(Path.home()/'.Trash')/('Y700-wifi-runtime-'+uuid.uuid4().hex);trash.mkdir()
    journal=out/'trash-receipts.jsonl'
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(hooks),ELDEN_INPUT_MANIFEST=str(input_manifest),
             ELDEN_GENERATED_ROOTS=json.dumps([str(module/'out'),str(objects)]),ELDEN_BUILD_TRASH=str(trash),ELDEN_RETIRE_JOURNAL=str(journal),ELDEN_LLVM=str(a.llvm.resolve()))
    env['PATH']=str(hooks/'bin')+os.pathsep+str(Path(sys.executable).parent)+os.pathsep+env['PATH']
    fetch=module/'tools/fetch-sources.py';original_fetch=sha(fetch)
    fetch.write_text('from wifi_snapshot_check import check\ncheck()\n')
    with (out/'prepare.log').open('x') as log:
        subprocess.run(['bash',str(module/'tools/prepare.sh')],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    # Apply after the upstream pre-load hook, before compiling any MHI unit.
    # Keep the exact prior source for differential tests and historical audit.
    sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
    from MhiReadPatch import patch as patch_mhi_status
    mhi=module/'out/mhi-src/boot.c';before=mhi.read_bytes();after=patch_mhi_status(before)
    original_mhi=mhi.with_name('boot.before-status-read-fix')
    if original_mhi.exists():raise ValueError('MHI original source already exists')
    mhi.rename(original_mhi);mhi.write_bytes(after)
    write(out/'mhi-status-read-fix.json',{'original_sha256':hashlib.sha256(before).hexdigest(),
        'derived_sha256':hashlib.sha256(after).hexdigest(),
        'patch_source_sha256':sha(ROOT/'drivers/EldenWifi/peach/MhiReadPatch.py'),
        'hardware_operations':False})
    from PciMsiPatch import patch as patch_pci_msi
    if a.native_lifecycle:
        from PciLifecyclePatch import patch as patch_pci_msi
    pci=module/'src/nw_pci.c';before=pci.read_bytes();after=patch_pci_msi(before)
    original_pci=pci.with_name('nw_pci.before-msi-fix')
    if original_pci.exists():raise ValueError('PCI original source already exists')
    pci.rename(original_pci);pci.write_bytes(after)
    write(out/'pci-msi-fix.json',{'original_sha256':hashlib.sha256(before).hexdigest(),
        'derived_sha256':hashlib.sha256(after).hexdigest(),
        'patch_source_sha256':sha(ROOT/'drivers/EldenWifi/peach/PciMsiPatch.py'),
        'implementation_sha256':sha(ROOT/'drivers/EldenWifi/peach/PciMsi.inc'),
        'native_lifecycle':a.native_lifecycle,
        'lifecycle_source_sha256':sha(ROOT/'drivers/EldenWifi/peach/PciLifecyclePatch.py') if a.native_lifecycle else None,
        'hardware_operations':False})
    # The original prepare flow reads the already-qualified Linux+Peach layer;
    # its output may contain additional upstream OS/runtime transformations.
    subprocess.run([sys.executable,str(fetch),'--check'],env=env,check=True)
    # Each upstream pin-headers pass regenerates out/pinned. Install the new
    # Peach interface only after the last pass, preserving its exact bytes.
    pwrseq_header=module/'out/pinned/linux/pwrseq/qcom_wcn.h'
    pwrseq_header.parent.mkdir(parents=True,exist_ok=True)
    if pwrseq_header.exists():raise ValueError('Unexpected existing power interface')
    shutil.copyfile(base/'include/linux/pwrseq/qcom_wcn.h',pwrseq_header)
    write(module/'out/elden-prepared.json',identity)
    builder=git(a.board_repository,'show',BOARD+':scripts/build-ath12k-wifi.py').decode();original_builder=hashlib.sha256(builder.encode()).hexdigest()
    def replace(old,new):
        nonlocal builder
        if builder.count(old)!=1:raise ValueError('Sheng builder context changed: '+old[:70])
        builder=builder.replace(old,new)
    replace("subprocess.run(['bash', str(module / 'tools/fetch-sources.sh')], check=True, stdout=subprocess.DEVNULL)","subprocess.run([sys.executable, str(module / 'tools/fetch-sources.py'), '--check'], check=True, stdout=subprocess.DEVNULL)")
    replace("subprocess.run(['bash', str(module / 'tools/prepare.sh')], check=True, stdout=subprocess.DEVNULL)","assert (module / 'out/elden-prepared.json').is_file(), 'Missing prepared source identity'")
    replace('ThreadPoolExecutor(8)','ThreadPoolExecutor(4)')
    replace("'-Wno-incompatible-pointer-types', '-Wno-error', ",'')
    replace("'-w',", "'-Werror=implicit-function-declaration', '-DCONFIG_POWER_SEQUENCING_QCOM_WCN=1',")
    replace("llvm = Path(subprocess.run(['brew', '--prefix', 'llvm'], check=True, capture_output=True, text=True).stdout.strip()) / 'bin'","llvm = Path(__import__('os').environ['ELDEN_LLVM'])")
    replace('    r = subprocess.run(command, capture_output=True, text=True)','    r = subprocess.run(command, capture_output=True, text=True)\n    obj.with_suffix(".log").write_text(r.stdout+r.stderr)')
    code=out/'builder';code.mkdir();(code/'build.py').write_text(builder);(code/'kernel_target.py').write_text("TRIPLE='arm64-apple-ios17.0'\n")
    with (out/'build.log').open('x') as log:subprocess.run([sys.executable,str(code/'build.py'),str(module),str(objects)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    from audit_wifi_runtime import audit
    result=audit(out,a.llvm,a.kernel_reference)
    if not result.get('mhi_status_read_fix'):raise ValueError('MHI error-propagation fix absent from complete runtime')
    result.update(component_revision=COMPONENT,board_builder_revision=BOARD,original_builder_sha256=original_builder,
                  derived_builder_sha256=sha(code/'build.py'),replaced_fetch_validator_sha256=original_fetch,
                  source_identity=identity,legacy_station_linked=False)
    write(out/'result.json',result);print(json.dumps({k:result[k] for k in ('objects','unique_consumed_inputs','imports_missing_from_reference_kernel','retired_generated_entries','kernel_linked')}))
if __name__=='__main__':main()
