"""Add only the virtual Bluetooth node; real resources remain board-owned."""
import copy,struct
def name(node):
    values=[p for p in node['properties'] if p['name']=='name']
    if len(values)!=1:raise ValueError('Ambiguous ADT name')
    return bytes.fromhex(values[0]['hex']).rstrip(b'\0').decode()
def apply(base):
    result=copy.deepcopy(base)
    nodes=[n for n in result['tree']['children'] if name(n)=='arm-io']
    if len(nodes)!=1:raise ValueError('Expected one arm-io root')
    parent=nodes[0]
    if any(name(n)=='bluetooth' for n in parent['children']):raise ValueError('Bluetooth node already present')
    properties={'name':b'bluetooth\0','device_type':b'bluetooth\0',
                'transport-encoding':struct.pack('<I',1),'transport-speed':struct.pack('<I',8000000)}
    parent['children'].append({'properties':[{'name':k,'hex':v.hex()} for k,v in properties.items()],'children':[]})
    result.pop('sha256',None)
    return result
