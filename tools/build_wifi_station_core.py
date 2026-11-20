"""Rebuild only the existing helper-owner/launchd staging core for station assets."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def defs(p):return {n for n,v in global_symbols(Path(p)).items() if v[0]&0x0e}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['parent-kernel','assets','clean-build','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();prior=json.loads((a.parent_kernel/'result.json').read_text());row=prior['core'];assets=json.loads((a.assets/'result.json').read_text())
    if not assets.get('station_assets') or not assets['crypto_source_unchanged'] or assets['credentials_included']:raise ValueError('Invalid station assets')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);cmd=list(row['command']);ov=json.loads(Path(cmd[cmd.index('-ivfsoverlay')+1]).read_text())
    replacements={};inherited={};changes=[]
    for item in ov['roots']:
        old=Path(item['external-contents']);inherited[str(old)]=sha(old)
        if old.name=='EldenWifiServiceAssets.h':new=a.assets/old.name
        elif old.name=='EldenIconCpuCommon.inc':
            text=old.read_text();old_hash='b02572b5f0fd9e79790645ad33df708b24530295'
            expected='static const unsigned char expected[20]={'+','.join('0x'+old_hash[i:i+2] for i in range(0,40,2))+'};'
            replacement='static const unsigned char expected[20]={'+','.join('0x'+assets['helper_cdhash'][i:i+2] for i in range(0,40,2))+'};'
            if text.count(expected)!=1:raise ValueError('Existing exact helper-owner digest changed')
            data=text.replace(expected,replacement,1).encode();new=out/old.name
            if new.exists() and new.read_bytes()!=data:raise ValueError('Owner aliases differ')
            new.write_bytes(data)
        else:continue
        item['external-contents']=str(new);changes.append(item['name']);replacements[str(old)]=str(new)
    if not replacements:raise ValueError('No exact station assets/owner bindings')
    ov['roots'].append(dict(type='file',name=str(out/'EldenWifiServiceAssets.h'),**{'external-contents':str(a.assets/'EldenWifiServiceAssets.h')}))
    vfs=out/'overlay.json';vfs.write_text(json.dumps(ov,indent=2)+'\n');cmd[cmd.index('-ivfsoverlay')+1]=str(vfs);cmd[cmd.index('-o')+1]=str(out/'kern_exec.o')
    r=subprocess.run(cmd,cwd=a.clean_build/'units/working/kern_exec',capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    old=Path(row['command'][row['command'].index('-o')+1]);obj=out/'kern_exec.o'
    if sha(old)!=row['object_sha256'] or defs(old)!=defs(obj):raise ValueError('Station core interface changed')
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'kern_exec.asm').write_text(asm)
    if any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('Station core SIMD/initializer')
    for name,digest in inherited.items():
        if sha(name)!=digest:raise ValueError('Inherited core source changed')
    proof=dict(compiled=True,station_core=True,base=row,object_sha256=sha(obj),base_object_sha256=row['object_sha256'],command=cmd,
       assets=assets,owner_common_sha256=sha(out/'EldenIconCpuCommon.inc'),owner_common=str(out/'EldenIconCpuCommon.inc'),
       inherited_sources=inherited,replacements=replacements,source_inputs={'tools/build_wifi_station_core.py':sha(Path(__file__))},
       warnings=r.stderr.count(b'warning:'),hardware_tested=False,unchanged_owner_predicate_except_exact_helper_digest=True)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:proof[k] for k in ['compiled','object_sha256','warnings','hardware_tested']}))
if __name__=='__main__':main()
