"""Enable the existing Bluetooth runtime on an explicitly qualified station image."""
import tomllib

from battery_boot import arguments


def with_bluetooth(template, qualification):
    if not qualification or not all(qualification.get(key) is True for key in (
        'station_trial', 'wifi_battery_runtime_trial', 'sideband_pins_trial',
    )):
        raise ValueError('Bluetooth coexistence requires the station and board power profile')
    menu = tomllib.loads(template)
    primary = menu['entry'][0]
    args = primary['args']
    old = arguments(args)
    if old.get('ewt') != '1' or old.get('epd') != '0' or old.get('elden-ucsi-pdos') != '1':
        raise ValueError('Bluetooth coexistence requires the radio-only station menu')
    if 'elden-wcn-power' in old:
        raise ValueError('Unexpected existing Bluetooth mode')

    # epd defaults to 0. The PDO observer is optional while PD handoff is off.
    # Keep UCSI, battery admission, USB logging and recovery enabled.
    omit = {'epd', 'elden-ucsi-pdos'}
    tokens = [token for token in args.split() if token.partition('=')[0] not in omit]
    new_args = ' '.join([*tokens, 'elden-wcn-power=4'])
    expected = {key: value for key, value in old.items() if key not in omit}
    if arguments(new_args) != dict(expected, **{'elden-wcn-power': '4'}):
        raise ValueError('Unrelated station boot arguments changed')
    if len(new_args.replace('@SESSION@', '0' * 16).encode()) > 1023:
        raise ValueError('Coexistence entry exceeds the XNU boot argument buffer')

    title = 'Wi-Fi SM8750 WPA2 + Bluetooth and data + USB - TEST'
    old_args_line = f'args = "{args}"'
    old_title_line = f'title = "{primary["title"]}"'
    if template.count(old_args_line) != 1 or template.count(old_title_line) != 1:
        raise ValueError('Ambiguous station menu entry')
    updated = template.replace(old_args_line, f'args = "{new_args}"', 1)
    updated = updated.replace(old_title_line, f'title = "{title}"', 1)
    primary.update(args=new_args, title=title)
    if tomllib.loads(updated) != menu:
        raise ValueError('Coexistence changed the fallback or menu policy')
    return updated
