# --- INSIDE your main project file (e.g., poke_test.py) ---

import poke_device # Or your filename like poke_device
import platform
import ctypes # Needed to access WinError attributes if desired

TARGET_DRIVE_NUMBER = 1 # Example drive number

# Determine device ID based on OS (as before)
if platform.system() == "Windows":
    device_id = TARGET_DRIVE_NUMBER
elif platform.system() == "Linux":
    device_id = "/dev/sda" # Replace with actual
elif platform.system() == "Darwin":
    device_id = "/dev/disk2" # Replace with actual
else:
    print("Unsupported OS")
    exit()

try:
    data = poke_device.send_scsi_read10(device_id, lba=0, blocks=1)

except poke_device.ScsiError as e:
    print(f"SCSI command failed on device {device_id}: {e}")

# --- Catch OSError and check for permission issues ---
except OSError as e:
    is_permission_error = False
    # Check specifically for Windows error code 5 (ERROR_ACCESS_DENIED)
    if platform.system() == "Windows" and hasattr(e, 'winerror') and e.winerror == 5:
        is_permission_error = True
    # Could potentially check for Linux/macOS errno EACCES/EPERM here too
    # elif (platform.system() == "Linux" or platform.system() == "Darwin") and hasattr(e, 'errno') and e.errno in (errno.EACCES, errno.EPERM):
    #    is_permission_error = True # Requires importing errno

    if is_permission_error:
        print(f"Permission Error: Access denied accessing device '{device_id}'.")
        print("Please run the script with Administrator privileges.")
    else:
        # Handle other OS errors (disk not found, etc.)
        print(f"OS Error interacting with device '{device_id}': {e}")
# --- End OSError handling ---

except FileNotFoundError as e: # Catch this specifically if needed (Linux/macOS mainly)
    print(f"Device Error: {e}. Check the device path/number.")

except (ValueError, NotImplementedError) as e:
    print(f"Error: {e}")

except Exception as e:
    print(f"An unexpected error occurred: {e}")
    import traceback
    traceback.print_exc() # Useful for debugging unexpected errors