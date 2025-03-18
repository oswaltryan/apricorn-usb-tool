import sys
import asyncio
import time
import logging
from windows_usb import find_apricorn_device, WinUsbDeviceInfo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

class UsbAutoLockTest:
    def __init__(self, poll_interval=10):
        self.poll_interval = poll_interval
        self.target_device = None

    async def select_device(self):
        logging.info("Searching for Apricorn device...")
        self.target_device = find_apricorn_device()
        if not self.target_device:
            logging.error("No Apricorn device found.")
            sys.exit(1)
        
        logging.info(f"Target device selected: {self.target_device.iProduct} ({self.target_device.idVendor}:{self.target_device.idProduct})")
        logging.info(f"Device Serial: {self.target_device.iSerial}, Protocol: {self.target_device.usb_protocol}")
        logging.info("Press ENTER to start the test.")
        await asyncio.to_thread(input)

    async def autolock_test(self, minutes):
        start = time.time()
        end = start + minutes * 60

        while time.time() < end:
            current_device = find_apricorn_device()
            elapsed = int(time.time() - start)

            if current_device is None:
                logging.error(f"Device removed too early at {elapsed}s; expected ~{minutes}m.")
                return False
            elif current_device.iSerial != self.target_device.iSerial:
                logging.error(f"Unexpected device change detected at {elapsed}s.")
                return False

            logging.info(f"Time Elapsed: {elapsed}s | Device Active: {current_device.iProduct} ({current_device.iSerial})")
            await asyncio.sleep(self.poll_interval)

        final_check = find_apricorn_device()
        if final_check is None:
            logging.info(f"Device removed as expected after {minutes}m.")
            return True

        logging.error(f"Device still present after {minutes}m.")
        return False

    async def run_tests(self):
        await self.select_device()
        intervals = [5, 10, 20]
        results = []

        for i, m in enumerate(intervals):
            logging.info(f"Starting auto-lock test for {m}m...")
            passed = await self.autolock_test(m)
            results.append(passed)
            logging.info(f"Test {'PASS' if passed else 'FAIL'} for {m}m.")

            if i < len(intervals) - 1:
                logging.info("Press ENTER to proceed to the next test.")
                await asyncio.to_thread(input)

        all_pass = all(results)
        logging.info(f"Overall test result: {'PASS' if all_pass else 'FAIL'}")
        return all_pass

if __name__ == "__main__":
    test = UsbAutoLockTest()
    overall = asyncio.run(test.run_tests())
    sys.exit(0 if overall else 1)
