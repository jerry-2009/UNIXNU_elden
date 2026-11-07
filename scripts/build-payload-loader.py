#!/usr/bin/env python3
"""Build only the standalone compressed-payload application on the Mac.

The accepted Pakala firmware and its build configuration are not replaced.
"""
import hashlib
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
MU=ROOT/'third_party/mu_wide_platforms'
BASE=MU/'MU_BASECORE'
TOOLS=BASE/'BaseTools'
WORK=ROOT/'out/payload-loader-20261106'
CONF=WORK/'Conf'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--toolchain',type=Path,default=Path.home()/'toolchains/llvm-20/bin')
LLVM=parser.parse_args().toolchain.resolve()
CONF.mkdir(parents=True,exist_ok=True)
for name in ('target','tools_def','build_rule'):
    shutil.copyfile(TOOLS/'Conf'/(name+'.template'),CONF/(name+'.txt'))
for name in ('clang','lld-link','llvm-lib','llvm-rc'):
    if not (LLVM/name).is_file():raise SystemExit('missing tool '+str(LLVM/name))
env=dict(os.environ)
env.update(WORKSPACE=str(MU),PACKAGES_PATH=os.pathsep.join(map(str,[ROOT/'drivers',MU,MU/'Platforms',
    ROOT/'third_party/UniXNU/package',ROOT/'third_party/UniXNU/drivers/DarwinBoot',
    BASE,MU/'Common/MU',MU/'Common/MU_TIANO',MU/'Silicon/Arm/MU_TIANO'])),
    EDK_TOOLS_PATH=str(TOOLS),CONF_PATH=str(CONF),PYTHON_COMMAND=sys.executable,
    CLANG_BIN=str(LLVM)+os.sep)
env['PATH']=os.pathsep.join([str(LLVM),str(TOOLS/'BinWrappers/PosixLike'),str(TOOLS/'Source/C/bin'),env['PATH']])
command=[str(TOOLS/'BinWrappers/PosixLike/build'),'-p','EldenPayloadLoader/EldenPayloadLoader.dsc',
         '-a','AARCH64','-b','DEBUG','-t','CLANGPDB','-n','4']
(WORK/'command.json').write_text(json.dumps(command,indent=2)+'\n')
with (WORK/'build.log').open('w') as log:
    result=subprocess.run(command,cwd=MU,env=env,stdout=log,stderr=subprocess.STDOUT)
(WORK/'result.json').write_text(json.dumps({'returncode':result.returncode})+'\n')
if result.returncode:
    print((WORK/'build.log').read_text()[-8000:])
    raise SystemExit(result.returncode)
source=MU/'Build/EldenPayloadLoader/DEBUG_CLANGPDB/AARCH64/EldenPayloadLoader.efi'
destination=WORK/source.name
shutil.copyfile(source,destination)
shutil.copyfile(source.with_name('EldenLoaderTest.efi'),WORK/'EldenLoaderTest.efi')
for name in ('EldenInitrdConsumer.efi','EldenRecoveryTest.efi','EldenFdtMailboxTest.efi','EldenBootMetadataTest.efi'):
    shutil.copyfile(source.with_name(name),WORK/name)
subprocess.run([str(TOOLS/'Source/C/bin/LzmaCompress'),'-e','-q','-o',
                str(WORK/'EldenInitrdConsumer.efi.lzma'),str(WORK/'EldenInitrdConsumer.efi')],check=True)
darwin=WORK/'DarwinBoot-plain-debug.efi'
shutil.copyfile(source.with_name('DarwinBoot.efi'),darwin)
darwin_source=ROOT/'third_party/UniXNU/drivers/DarwinBoot/DarwinBootPkg/Driver'
(WORK/'DarwinBoot-plain-debug.json').write_text(json.dumps(dict(
    sha256=hashlib.sha256(darwin.read_bytes()).hexdigest(),debug_library='BaseDebugLibNull',
    purpose='AAVMF handoff fixture; not the accepted Y700 FD binary',
    sources={name:hashlib.sha256((darwin_source/name).read_bytes()).hexdigest()
             for name in ('DarwinBoot.c','Entry.S','BootArgs.h','BootVideo.h')}),indent=2)+'\n')
report=dict(path=str(destination),bytes=destination.stat().st_size,
    sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),hardware_tested=False)
(WORK/'artifact.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
