"""Export pinned ArmSmmu4K code with an isolated Elden Wi-Fi symbol prefix."""
import argparse,hashlib,json,subprocess
from pathlib import Path
REV='83969cd874503e65997ff7639f7dcf3d0a92cd17'
FILES=['ArmSmmu4K.c','ArmSmmu4K.h','ArmSmmu4KContext.c','ArmSmmu4KContext.h',
       'ArmSmmu4KProgram.c','ArmSmmu4KProgram.h','ArmSmmu4KAudit.c','ArmSmmu4KAudit.h',
       'ArmSmmu4KTableMemory.c','ArmSmmu4KTableMemory.h','LICENSE']
def prepare(repository,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);records={}
    for name in FILES:
        raw=subprocess.check_output(['git','-C',str(repository),'show',REV+':'+name])
        data=raw if name=='LICENSE' else raw.replace(b'ArmSmmu4K',b'EldenWifiSmmu4K').replace(b'ARM_SMMU_4K',b'ELDEN_WIFI_SMMU_4K')
        target=name.replace('ArmSmmu4K','EldenWifiSmmu4K');(output/target).write_bytes(data)
        records[name]={'original_sha256':hashlib.sha256(raw).hexdigest(),'output':target,'output_sha256':hashlib.sha256(data).hexdigest()}
    report={'repository':'https://github.com/UniXNU/ArmSmmu4K','revision':REV,
            'transformation':'Replace ArmSmmu4K and ARM_SMMU_4K identifier/file/guard prefixes only; algorithms and original LICENSE unchanged','files':records}
    # Match the first reviewed manifest byte format on every host. The local
    # .gitattributes keeps Git from changing this hash-bound metadata file.
    (output/'source.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\r\n');return report
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repository',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(prepare(a.repository,a.output)))
if __name__=='__main__':main()
