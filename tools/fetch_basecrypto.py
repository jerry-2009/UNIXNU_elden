#!/usr/bin/env python3
"""Fetch the pinned public Project Mu CryptoBin package and verify all994 inputs.

No compiler or tablet is required. Only a new output directory is populated;
existing files, failed downloads and archives are never deleted by this tool.
"""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,stat,tempfile,urllib.request,uuid,zipfile
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while block:=f.read(1<<20):h.update(block)
    return h.hexdigest()
def verify_archive(path,lock):
    if path.stat().st_size!=lock['bytes'] or sha(path)!=lock['sha256']:
        raise ValueError('Archive does not match the pinned public release: '+str(path))
def main():
    p=argparse.ArgumentParser(description=__doc__);mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output',type=Path,help='New extraction directory; use this root for the crypto input')
    mode.add_argument('--check',type=Path,help='Read-only verification of an existing extraction')
    p.add_argument('--archive',type=Path,help='Use an already downloaded ZIP instead of fetching')
    p.add_argument('--cache-dir',type=Path,default=Path(tempfile.gettempdir())/'unixnu-elden-downloads')
    a=p.parse_args();lock=json.loads((ROOT/'config/basecrypto.lock.json').read_text())
    expected=json.loads((ROOT/lock['manifest']).read_text())['crypto_files']
    if len(expected)!=lock['files']:raise ValueError('Crypto manifest count differs')
    output=(a.output or a.check).resolve();archive=None
    if a.output:
        if output.exists():raise ValueError('Output already exists; use --check or choose a new directory')
        if a.archive:archive=a.archive.resolve(strict=True)
        else:
            cache=a.cache_dir.resolve();cache.mkdir(parents=True,exist_ok=True);archive=cache/lock['asset']
            if not archive.exists():
                partial=cache/(lock['asset']+'.'+uuid.uuid4().hex+'.part')
                print('Downloading '+lock['url'],flush=True)
                request=urllib.request.Request(lock['url'],headers={'User-Agent':'UniXNU-Elden-BaseCrypto'})
                with urllib.request.urlopen(request,timeout=60) as response,partial.open('xb') as f:
                    while block:=response.read(1<<20):f.write(block)
                verify_archive(partial,lock)
                if archive.exists():verify_archive(archive,lock)
                else:partial.rename(archive)
        verify_archive(archive,lock)
        with zipfile.ZipFile(archive) as z:
            files=[i for i in z.infolist() if not i.is_dir()]
            if len(files)!=len(expected) or {i.filename for i in files}!=set(expected):raise ValueError('ZIP member set differs from firmware manifest')
            seen=set()
            for info in files:
                name=PurePosixPath(info.filename)
                if name.is_absolute() or '..' in name.parts or '\\' in info.filename or ':' in info.filename or stat.S_ISLNK(info.external_attr>>16):raise ValueError('Unsafe archive path')
                key=info.filename.casefold()
                if key in seen:raise ValueError('Case-colliding archive paths')
                seen.add(key)
                if not (output/Path(*name.parts)).resolve().is_relative_to(output):raise ValueError('Archive path escapes output')
            output.mkdir(parents=True,exist_ok=False)
            for info in files:
                dest=output/Path(*PurePosixPath(info.filename).parts);dest.parent.mkdir(parents=True,exist_ok=True)
                h=hashlib.sha256()
                with z.open(info) as src,dest.open('xb') as dst:
                    while block:=src.read(1<<20):dst.write(block);h.update(block)
                if h.hexdigest()!=expected[info.filename]:raise ValueError('Extracted input hash differs: '+info.filename)
    else:
        for name,digest in expected.items():
            if sha(output/name)!=digest:raise ValueError('Crypto input differs: '+name)
    print(json.dumps({'verified':True,'source':lock['repository'],'release':lock['release'],'archive_sha256':lock['sha256'],
        'verified_files':len(expected),'crypto':str(output),'archive':str(archive) if archive else None,'device_operation':False},indent=2))
if __name__=='__main__':main()
