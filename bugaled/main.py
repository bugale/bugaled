import time
import tempfile
import logging
import sys
import contextlib
import subprocess
from typing import Iterator

import psutil
from openrgb import OpenRGBClient
from openrgb.utils import RGBColor


CYCLE_TIME = 2
FPS = 180
STEPS = int(FPS * CYCLE_TIME)
CLOCKWISE = True

OPENRGB_PATH = r'C:\Program Files\OpenRGB\OpenRGB.exe'
QLFAN_PARTS = [4, 6, 12, 12]
OBSIDIAN_LEDS = 22
RING_LEDS = 24


class Devices:
    def __init__(self, client: OpenRGBClient) -> None:
        self.client = client
        self.gpu = client.get_devices_by_name('ASUS ROG STRIX LC 3080Ti O12G GAMING')[0]
        self.mobo = client.get_devices_by_name('ASUS ROG MAXIMUS Z690 EXTREME')[0]
        self.case = client.get_devices_by_name('Corsair 1000D Obsidian')[0]
        self.cpu = client.get_devices_by_name('Corsair Commander Core')[0]
        self.nodes = client.get_devices_by_name('Corsair Lighting Node Core')
        assert len(self.nodes) >= 2


@contextlib.contextmanager
def get_devices() -> Iterator[Devices]:
    try:
        for proc_ in psutil.process_iter():
            try:
                if proc_.exe().lower() == OPENRGB_PATH.lower():
                    proc_.kill()
            except Exception:
                logging.exception('Failed to kill OpenRGB')
    except Exception:
        logging.exception('Failed to kill OpenRGB')
    proc = subprocess.Popen([OPENRGB_PATH, '--server'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')
    try:
        devices = None
        for _ in range(60):
            time.sleep(10)
            try:
                devices = Devices(OpenRGBClient())
                break
            except Exception:
                logging.debug('OpenRGB not ready yet', exc_info=True)
        if not devices:
            devices = Devices(OpenRGBClient())
        yield devices
    finally:
        try:
            proc.kill()
            proc.wait()
            assert proc.stdout
            assert proc.stderr
            logging.info('OpenRGB exited with code %d, %s%s', proc.returncode, proc.stdout.read(), proc.stderr.read())
        except Exception:
            logging.exception('Failed to kill OpenRGB')


def run() -> None:
    with get_devices() as devices:
        # Hardware-controlled devices
        devices.gpu.set_mode('rainbow')
        devices.mobo.set_mode('rainbow')

        # Software-controlled devices
        devices.case.set_mode('direct')
        devices.case.zones[0].resize(OBSIDIAN_LEDS)
        devices.case.zones[1].resize(0)
        devices.cpu.set_mode('direct')
        for zone in devices.cpu.zones[1:-1]:
            zone.resize(sum(QLFAN_PARTS))
        devices.cpu.zones[-1].resize(sum(QLFAN_PARTS) + RING_LEDS - len(devices.cpu.zones[0].colors))  # Adjust for unchangable incorrect ring LED count
        for node in devices.nodes:
            node.set_mode('direct')
            node.zones[0].resize(sum(QLFAN_PARTS) * 6)
            node.zones[1].resize(0)

        def float_range(length: int) -> list[float]:
            return [i / length for i in range(length)]

        def rgb_from_float(flt: float) -> RGBColor:
            return RGBColor.fromHSV(int(flt * 360) % 360, 100, 100)

        ql_float_range: list[float] = sum((float_range(part) for part in QLFAN_PARTS), [])
        ranges = [
            (devices.case, float_range(len(devices.case.colors))),
            (devices.cpu, float_range(RING_LEDS) + ql_float_range * 6)
        ] + [(node, ql_float_range * 6) for node in devices.nodes]

        steps = [[(device, [rgb_from_float(f + i / STEPS) for f in range_]) for device, range_ in ranges] for i in list(range(STEPS))[::-1 if CLOCKWISE else 1]]

        while True:
            start = time.time()
            for device, _ in ranges:
                device.update()
            for i in range(STEPS):
                for device, range_ in steps[i]:
                    device.set_colors(range_)
                time_to_sleep = (start + (i * CYCLE_TIME) / STEPS) - time.time()
                if time_to_sleep > 0.01:
                    time.sleep(time_to_sleep)


def main() -> None:
    with tempfile.NamedTemporaryFile(mode='w', prefix='bugaled', suffix='.txt', delete=False) as log_file:
        pass
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler_stream = logging.StreamHandler(sys.stdout)
    handler_stream.setLevel(logging.DEBUG)
    handler_stream.setFormatter(formatter)
    root.addHandler(handler_stream)
    handler_file = logging.FileHandler(log_file.name)
    handler_file.setLevel(logging.DEBUG)
    handler_file.setFormatter(formatter)
    root.addHandler(handler_file)
    logging.info('Bugaled started')
    try:
        run()
    except Exception:
        logging.exception('Bugaled crashed')
        raise


if __name__ == '__main__':
    main()
