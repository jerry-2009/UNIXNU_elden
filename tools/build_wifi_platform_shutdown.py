"""Build the actual platform-shutdown callback without changing removal semantics."""
import argparse,hashlib,json,re,subprocess,sys,shlex
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from PlatformShutdownPatch import patch as platform_patch
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def defs(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(p).items() if not v[0]&0x0e}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['runtime-build','lifecycle-build','init-build','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base=a.runtime_build.resolve();life=a.lifecycle_build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    baseline=read(base/'result.json');manifest=read(base/'objects/build-report.json');lr=read(life/'result.json');initial=read(a.init_build/'result.json')
    assert initial['init_trace'] and initial['units']==125
    for f,h in initial['compile_inputs'].items():assert sha(Path(f))==h,f
    assert baseline['objects']==len(manifest['objects'])==125 and lr['native_lifecycle_required']
    assert sha(base/'objects/build-report.json')==baseline['build_report_sha256']
    for f,h in baseline['consumed_inputs'].items():assert sha(Path(f))==h,f
    header=ROOT/'drivers/EldenWifi/PlatformShutdownApi.h'
    rename=dict(line.split() for line in (base/'objects/rename.txt').read_text().splitlines())
    changes={};records={};dependencies={}
    for objname,source_name in [('nw_wifi.o','nw_wifi.c'),('nw_pci.o','nw_pci.c')]:
        row,=[r for r in manifest['objects'] if Path(r['path']).name==objname]
        original=Path(row['source']);assert sha(original)==row['source_sha256']
        data=platform_patch(source_name,original.read_bytes());source=out/source_name;source.write_bytes(data)
        identity=read(base/'objects/raw'/objname.replace('.o','.inputs.json'));cmd=list(identity['command'])
        assert all(baseline['consumed_inputs'].get(n)==h for n,h in identity['dependencies'].items())
        assert cmd[cmd.index('-target')+1]=='arm64-apple-ios17.0' and '-mgeneral-regs-only' in cmd
        cmd+=['-I',str(header.parent)]
        raw=out/objname.replace('.o','.raw.o');obj=out/objname;dep=out/objname.replace('.o','.d')
        cmd[cmd.index(str(original))]=str(source);cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep)
        r=subprocess.run(cmd,cwd=out,capture_output=True);(out/(objname+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        inputs=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
        assert set(inputs)-{str(source),str(header)}==set(identity['dependencies'])-{str(original)}
        for f in inputs:assert sha(Path(f))==(sha(source) if f==str(source) else sha(header) if f==str(header) else identity['dependencies'][f]);dependencies[f]=sha(Path(f))
        subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
        assert global_symbols(obj)=={rename.get(n,n):v for n,v in global_symbols(raw).items()}
        extra={'_nw_wifi_platform_shutdown'} if objname=='nw_wifi.o' else {'_elden_nw_pci_platform_shutdown'}
        assert sections(raw)==sections(obj) and defs(obj)==defs(Path(row['path']))|extra
        assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/(objname+'.asm')).write_text(asm,encoding='utf-8')
        assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
        changes[objname]=obj;records[objname]={'source_sha256':sha(source),'object_sha256':sha(obj),'warnings':r.stderr.count(b'warning:'),'command':cmd}
    pci=life/'nw_pci.o';assert sha(pci)==lr['object_sha256']
    cfg=a.init_build/'cfg80211_core.o';assert sha(cfg)==initial['rebuilt_units']['cfg80211_core.o']['object_sha256'];changes['cfg80211_core.o']=cfg
    objects=[];kept={};definitions=set();imports=set()
    for row in manifest['objects']:
        original=Path(row['path']);assert sha(original)==row['object_sha256'];f=changes.get(original.name,original)
        symbols=defs(f);assert not definitions&symbols;definitions|=symbols;imports|=refs(f);objects.append(f)
        if f==original:kept[str(f)]=sha(f)
    target=out/'WifiRuntimeMsiBinding.o'
    r=subprocess.run(['xcrun','ld','-r','-arch','arm64','-platform_version','ios','17.0','17.0','-o',str(target),*map(str,objects)],capture_output=True)
    (out/'link.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    assert defs(target)==definitions and refs(target)==imports-definitions==set(lr['imports'])
    for f,h in baseline['consumed_inputs'].items():assert sha(Path(f))==h,f
    own={**lr['source_sha256'],**initial['source_sha256'],**{n:sha(ROOT/n) for n in ['drivers/EldenWifi/peach/PlatformShutdownPatch.py','drivers/EldenWifi/PlatformShutdownApi.h','tools/build_wifi_platform_shutdown.py']}}
    result={'compiled':True,'units':125,'native_lifecycle_required':True,'init_trace':True,'platform_shutdown':True,'removal_unchanged':True,'retained_cfg_init':sha(cfg),'prior_lifecycle_reference':sha(pci),'rebuilt_units':records,'retained_objects':kept,
            'binding_sha256':sha(target),'imports':sorted(refs(target)),'source_sha256':own,'compile_inputs':dependencies,'hardware':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'compiled':True,'binding':result['binding_sha256'],'kept':len(kept),'warnings':{n:r['warnings'] for n,r in records.items()}}))
if __name__=='__main__':main()
