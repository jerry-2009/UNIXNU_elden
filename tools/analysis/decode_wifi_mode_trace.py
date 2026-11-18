"""Interpret mode/capability/event metadata in a validated CE3 sequence."""
import argparse
import hashlib
import json
from pathlib import Path
from decode_wifi_ce3_flow import decode as decode_flow

MODE, EVENT, CAPS, PDEV = 0x4d4f4445, 0x45564e54, 0x43415053, 0x50444556


def decode(raw):
    result = decode_flow(raw)
    mode_events = []
    for event in result["events"]:
        a, b, marker, d, e = event["fields"]
        if event["kind"] != "wmi-request" or marker not in (MODE, EVENT, CAPS, PDEV):
            continue
        event.pop("command", None)
        if marker == MODE:
            event.update(kind="mode-request", requested_mode=a, preferred_mode=b,
                         advertised_modes=d, decoded_dbs=bool(e & 1), decoded_sbs=bool(e & 2))
        elif marker == EVENT:
            event.update(kind="firmware-event", event_id=a, frame_bytes=b, preferred_mode=e)
        elif marker == CAPS:
            event.update(kind="firmware-mode-cap", mode_id=a, phy_map=b, config_type=d, advertised_modes=e)
        else:
            event.update(kind="firmware-pdev-cap", pdev_id=a, mode_id=b, phy_id=d, supported_bands=e)
        mode_events.append(event)
    if not any(event["kind"] == "mode-request" for event in mode_events):
        raise ValueError("No actual mode request metadata")
    result.update(mode_events=mode_events, metadata_only=True,
                  firmware_mode_success_unproven=True, network_accepted=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.capture.read_bytes()
    result = decode(raw)
    result.update(capture_sha256=hashlib.sha256(raw).hexdigest(), capture_bytes=len(raw))
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("claimed", "emitted", "dropped", "bounded_trace_complete")}))


if __name__ == "__main__":
    main()
