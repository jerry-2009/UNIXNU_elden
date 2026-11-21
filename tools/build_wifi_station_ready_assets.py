"""Rebuild the same signed 802.1X helper/cache with pre-association readiness."""
import hashlib,json,sys
from pathlib import Path
import build_wifi_station_assets as assets
ROOT=Path(__file__).resolve().parents[1];STA=ROOT/'drivers/EldenWifi/portable/station'
sys.path.insert(0,str(STA));from ProfileReadySource import helper
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    original=assets.source
    assets.source=lambda:helper(original())
    assets.main()
    # Arguments remain exactly the original builder's explicit input/output.
    out=Path(sys.argv[sys.argv.index('--output')+1]);p=out/'result.json';r=json.loads(p.read_text())
    r.update(helper_profile_ready=True,crypto_source_unchanged=False,crypto_algorithms_unchanged=True,ready_generation_status_only=True,
        helper_source_sha256=sha(out/'elden-wifi-supplicant.c'))
    r['source_inputs'].update({n:sha(ROOT/n) for n in ['tools/build_wifi_station_ready_assets.py','drivers/EldenWifi/portable/station/ProfileReadySource.py','drivers/EldenWifi/portable/station/ProfileReady.h']})
    p.write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':main()
