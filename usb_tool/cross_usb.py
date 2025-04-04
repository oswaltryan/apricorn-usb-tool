import platform
import cProfile
import pstats
import io
import re

def main():
    if platform.system().lower().startswith("win"):
        from usb_tool import windows_usb
        devices = windows_usb.find_apricorn_device()
    else:
        from usb_tool import linux_usb
        devices = linux_usb.find_apricorn_device()

    if not devices:
        print("No Apricorn devices found.")
    else:
        for idx, dev in enumerate(devices, start=1):
            print(f"\n=== Apricorn Device #{idx} ===")
            for field_name, value in dev.__dict__.items():
                print(f"  {field_name}: {value}")
    print()

def runtime_check():
    pr = cProfile.Profile()
    pr.enable()

    if platform.system().lower().startswith("win"):
        from usb_tool import windows_usb
        devices = windows_usb.find_apricorn_device()
    else:
        from usb_tool import linux_usb
        devices = linux_usb.find_apricorn_device()

    pr.disable()
    s = io.StringIO()
    sortby = pstats.SortKey.CUMULATIVE  # or 'time', 'cumulative'
    ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
    ps.print_stats()

    output = s.getvalue()  # Capture the full stats output

    # Find the line containing the function call counts and total time
    summary_line = next((line for line in output.splitlines() if "function calls" in line), None)

    if summary_line:
        start_index = summary_line.find("in ")
        end_index = summary_line.find("seconds")

        if start_index != -1 and end_index != -1 and start_index < end_index:
            sliced_string = summary_line[start_index : end_index + len("seconds")]
            sliced_string = float(sliced_string[3:8])
            print()
            print(f"Runtime: {sliced_string}s")
            print()
        else:
            print("Could not parse the summary line.")
    else:
        print("Summary line with function call information not found in the output.")

    # Save the profile data to a file (optional)
    # pr.dump_stats("usb_profile.prof")

    # print("\n--- Full Profile Statistics ---")
    # print(output)  # Print the full stats to the console
    # print()