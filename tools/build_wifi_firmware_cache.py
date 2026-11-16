"""Build native firmware caching and reuse the qualified FAT/kernel providers."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from replay_xnu_objects import sections,global_symbols
ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def defs(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(p).items() if not v[0]&0x0e}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['clean-build','reference-kernel','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);base=a.clean_build.resolve();d=ROOT/'drivers/EldenWifi'
    row=read(base/'units/result.json')['units']['WcnPowerNative'];cmd=list(row['command']);overlay=read(Path(cmd[cmd.index('-ivfsoverlay')+1]));assert overlay['fallthrough'] is False
    directories=set();inherited={}
    for item in overlay['roots']:
        f=Path(item['external-contents']);inherited[str(f)]=sha(f)
        if item['name'].endswith('/WcnPowerNative.cpp'):
            assert sha(f)=='5c16106e90622150686b90706fcfc8c674cf3c4d563ed782fd7d57fc864e2c72'
            directories.add(str(Path(item['name']).parent));item['external-contents']=str(d/'FirmwareCache.cpp')
    assert directories
    files={n:d/n for n in ['FirmwareCache.h','ModemFiles.h']}
    files.update({'FatVolume.h':ROOT/'drivers/EldenPmicGlink/FatVolume.h','EldenWifiResources.h':ROOT/'soc/sm8750/include/EldenWifiResources.h','EldenWifiFirmwareInputs.h':ROOT/'package/EldenWifiFirmwareInputs.h'})
    existing={x['name']:x for x in overlay['roots']}
    for directory in directories:
        for name,path in files.items():
            key=str(Path(directory)/name)
            if key in existing:assert sha(Path(existing[key]['external-contents']))==sha(path),'VFS collision '+key
            else:overlay['roots'].append({'type':'file','name':key,'external-contents':str(path)})
    (out/'overlay.json').write_text(json.dumps(overlay,indent=2)+'\n');cmd[cmd.index('-ivfsoverlay')+1]=str(out/'overlay.json');cmd[cmd.index('-o')+1]=str(out/'FirmwareCache.o')
    records={};objects=[]
    plain=['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-std=c11','-O2','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-stack-protector','-mgeneral-regs-only','-I'+str(d),'-I'+str(ROOT/'drivers/EldenPmicGlink')]
    for name,command,cwd in [('FirmwareCache',cmd,base/'units/working/WcnPowerNative'),('ModemFiles',[*plain,'-c',str(d/'ModemFiles.c'),'-o',str(out/'ModemFiles.o')],out)]:
        r=subprocess.run(command,cwd=cwd,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode();obj=out/(name+'.o');objects.append(obj)
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/(name+'.asm')).write_text(asm,encoding='utf-8')
        assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
        assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
        records[name]={'sha256':sha(obj),'exports':sorted(defs(obj)),'imports':sorted(refs(obj)),'warnings':r.stderr.count(b'warning:'),'command':command}
    target=out/'FirmwareCacheBinding.o'
    r=subprocess.run(['xcrun','ld','-r','-arch','arm64','-platform_version','ios','17.0','17.0','-o',str(target),*map(str,objects)],capture_output=True)
    (out/'link.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    union=set().union(*(defs(p) for p in objects));pending=set().union(*(refs(p) for p in objects))-union
    assert defs(target)==union and refs(target)==pending
    assert pending<=defs(a.reference_kernel),sorted(pending-defs(a.reference_kernel))
    for n,h in inherited.items():assert sha(Path(n))==h,n
    inputs={str(f.relative_to(ROOT)):sha(f) for f in [d/'FirmwareCache.cpp',d/'ModemFiles.c',*files.values(),Path(__file__)]}
    result={'compiled':True,'objects':records,'binding_sha256':sha(target),'remaining_imports':sorted(pending),'kernel_imports_verified':True,
            'qdss_config_available':True,
            'reference_kernel_sha256':sha(a.reference_kernel),'source_inputs':inputs,'scalar':True,'kernel_linked':False,'hardware':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['compiled','binding_sha256','remaining_imports','kernel_imports_verified']}))
if __name__=='__main__':main()
