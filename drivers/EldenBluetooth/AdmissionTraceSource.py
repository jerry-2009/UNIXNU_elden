"""Report existing admission snapshots only on a refused power preparation."""
import hashlib
ORIGINAL='5c16106e90622150686b90706fcfc8c674cf3c4d563ed782fd7d57fc864e2c72'

def source(original):
    if hashlib.sha256(original).hexdigest()!=ORIGINAL:raise ValueError('WCN native source differs')
    text=original.decode();old='        if(rc){retained=true;goto done;} // maps and uncertain shared votes remain held'
    assert text.count(old)==1
    new='''        if(rc){
            for(unsigned i=0;i<EldenWcnRailCount;i++){
                const EldenWcnRailState &s=c->power.before[i];
                log("\\nELDEN_WCN admission-stored rail=%u mv=%u enable=%02x mode=%02x status=%02x range=%u/%u; unread slots may be zero\\n",
                    i,s.mv,s.enable,s.mode,s.status,elden_wcn_rail_specs[i].minimum,elden_wcn_rail_specs[i].maximum);
            }
            retained=true;goto done;
        } // maps and uncertain shared votes remain held'''
    return text.replace(old,new).encode()
