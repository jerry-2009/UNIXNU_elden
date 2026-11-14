"""Check explicit original inputs before an expensive source build starts."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def check(inputs,variant,target):
    def expect(name,value):
        if sha(inputs[name])!=value:raise ValueError('Original input fingerprint differs: '+name)
    expect('original_agent','dd01b74e4413e0bb72de4a62f3f7675deb5026cad79d376fde6570abd0d012f8')
    expect('nvt_firmware','413216d0e8738078414fa681262439ab6d1c181f02974215e0394f102fcc08dc')
    ip=json.loads((ROOT/'profiles/v91/image-build/plan.json').read_text())
    expect('original_kernelcache',ip['prelink']['original_kernelcache_sha256'])
    for tool in ('clang','llvm-objcopy'):
        if not (inputs['llvm']/tool).is_file():raise ValueError('LLVM tool missing: '+tool)
    subprocess.run(['xcrun','--sdk','iphoneos','--find','clang'],check=True,stdout=subprocess.DEVNULL)
    if variant=='bluetooth':
        for row in json.loads((ROOT/'profiles/v110-bt-fifo/plan.json').read_text())['firmware']:
            f=inputs['wcn_firmware']/row['file']
            if not f.is_file() or f.stat().st_size!=row['bytes'] or sha(f)!=row['sha256']:raise ValueError('Original WCN firmware differs: '+row['file'])
    if target=='boot':
        if os.geteuid() not in (0,501):raise ValueError('The frozen Data fixture requires macOS UID501 or root; kernel-only builds have no such requirement')
        expect('os_image','d8808bea18b949142b3e47bbcb780c3f22faaacd9b40a88f77c23557181edc9c')
        fp=json.loads((ROOT/'profiles/v91/firmware-build/plan.json').read_text())
        for rel,digest in fp['crypto_files'].items():
            if sha(inputs['crypto']/rel)!=digest:raise ValueError('Original Crypto input differs: '+rel)
        for name,key in [('mu_repository','mu_commit'),('unixnu_repository','unixnu_commit')]:
            subprocess.run(['git','-C',str(inputs[name]),'cat-file','-e',fp[key]+'^{commit}'],check=True)
        sys.path.insert(0,str(ROOT/'tools/device'));from avb_guard import check_image
        boot=check_image(inputs['stock_boot'],'boot_a');check_image(inputs['parent_vbmeta'],'vbmeta')
        ACCEPTED_STOCK={'8b8e72dad85a65d3bf6fc2c6b2a88064d0487e4696ae578e9fd4c46a33565890','4e4c9c72707c7cb91c29a2ccece15ca919a3fa2098cea795e28ed22dfdcd86fc'}
        if boot.sha256 not in ACCEPTED_STOCK:raise ValueError('Wrong stock boot template (accepted: original testlab baseline or Jerry-local rebuild from ArmadaOS boot_a)')
        if not inputs['avbtool'].is_file() or not inputs['signing_key'].is_file():raise ValueError('Signing inputs absent')
    return {'original_inputs_verified':True,'variant':variant,'target':target,'device_operation':False}
