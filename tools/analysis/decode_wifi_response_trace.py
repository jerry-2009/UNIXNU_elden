"""Decode verified HW-mode status and CE3 config observations without packet data."""
import argparse
import hashlib
import json
from pathlib import Path
from decode_wifi_mode_trace import decode as decode_mode

RESPONSE,REFUSED,RING,EXPECTED,POINTER,CPUMAP=0x5253504d,0x52454655,0x52494e47,0x45585043,0x50545253,0x4350554d
def decode(raw):
    result=decode_mode(raw);extra=[]
    for event in result['events']:
        a,b,marker,d,e=event['fields']
        if event['kind']!='wmi-request' or marker not in (RESPONSE,REFUSED,RING,EXPECTED,POINTER,CPUMAP):continue
        event.pop('command',None)
        if marker==RESPONSE:event.update(kind='mode-response',status=a,configured_mode=b,pdev_id=d,mappings=e)
        elif marker==REFUSED:event.update(kind='mode-response-refused',frame_bytes=a,tag=b,tlv_bytes=d,reason=e)
        elif marker==RING:event.update(kind='ce3-config',base_low=a,base_high=b,misc=d,ring_id_word=e)
        elif marker==EXPECTED:event.update(kind='ce3-config-expected',ring_base=a,base_high=b,ring_id_word=d,r0_base=e)
        elif marker==POINTER:event.update(kind='ce3-pointer-config',low=a,high=b,expected=d,enable_mask=e)
        else:event.update(kind='cpu-bar-map',par=a,virtual_address=b,shadow_offset=d,
                          attribute=(a>>56)&255,translation_fault=bool(a&1))
        extra.append(event)
    responses=[event for event in extra if event['kind']=='mode-response']
    requests=[event for event in result['mode_events'] if event['kind']=='mode-request']
    if len(responses)>1:raise ValueError('Multiple mode responses in one bounded startup')
    result['response_observations']=extra
    result['mode_status_verified']=bool(responses)
    result['mode_transition_success_unproven']=not bool(responses)
    result['firmware_mode_success_unproven']=not bool(responses)
    if responses:
        result['mode_command_succeeded']=responses[0]['status']==0 and responses[0]['configured_mode']==requests[0]['requested_mode']
    configs=[event for event in extra if event['kind']=='ce3-config']
    expect=[event for event in extra if event['kind']=='ce3-config-expected']
    pointers=[event for event in extra if event['kind']=='ce3-pointer-config']
    if len(configs)==len(expect)==len(pointers)==1:
        actual,wanted,pointer=configs[0],expect[0],pointers[0]
        result['ce3_config_matches']=actual['base_low']==(wanted['ring_base']&0xffffffff) and actual['base_high']==wanted['base_high'] and actual['ring_id_word']==wanted['ring_id_word'] and (pointer['low']|(pointer['high']<<32))==pointer['expected']
        result['ce3_enable_observed']=bool(actual['misc']&pointer['enable_mask'])
    result['network_accepted']=False
    return result
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('capture',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    raw=args.capture.read_bytes();result=decode(raw);result.update(capture_sha256=hashlib.sha256(raw).hexdigest(),capture_bytes=len(raw))
    with args.output.open('x',encoding='utf-8') as output:output.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:value for key,value in result.items() if key in ('mode_status_verified','mode_command_succeeded','ce3_config_matches','ce3_enable_observed')}))
if __name__=='__main__':main()
