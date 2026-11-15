"""Reject altered or incomplete evidence using an actual QD capture."""
import argparse,re
from pathlib import Path
from assess_ufs_queue import parse
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path);a=p.parse_args()
    text=a.capture.read_bytes().decode(errors='replace').replace('\r','');assert parse(text)['physical_overlap_observed'];cases=1
    rows=re.findall(r'^ELDEN_UFS_QD row .*$',text,re.M);assert len(rows)==48
    changed=[text.replace(rows[0]+'\n','',1),text+'\n'+rows[0]+'\n',
             text.replace('slots=32 entries=32 uncached=1','slots=16 entries=32 uncached=0',1),
             text.replace('read-par=44','read-par=ff',1),
             text.replace(rows[0],rows[0].replace('direct=32','direct=31'),1),
             text.replace(rows[0],rows[0].replace('commands=32','commands=31'),1),
             text.replace(rows[0],re.sub(r'db-peak=\d+','db-peak=33',rows[0]),1),
             text.replace(rows[0],re.sub(r'io-ns=\d+','io-ns=0',rows[0]),1),
             text.replace(rows[1],re.sub(r'sha=([0-9a-f])',lambda m:'sha='+('0' if m[1]!='0' else '1'),rows[1]),1),
             text.replace('ELDEN_UFS_QD end name=OS good=1','ELDEN_UFS_QD end name=OS good=0',1),
             text.replace('EldenRoot: OS complete SHA256 accepted;','EldenRoot: OS unproven;',1)]
    for bad in changed:
        try:parse(bad)
        except ValueError:cases+=1
        else:raise AssertionError('Changed evidence accepted')
    print(f'PASS {cases} captured QD assessor cases')
if __name__=='__main__':main()
