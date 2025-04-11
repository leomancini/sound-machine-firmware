#!/usr/bin/env python3
import os
import sys
import signal
import time
import subprocess
import re
import threading

def create_pipe():
    """Create the named pipe if it doesn't exist."""
    pipe_path = "/tmp/rfid_pipe"
    
    # Remove the pipe if it exists
    if os.path.exists(pipe_path):
        try:
            os.unlink(pipe_path)
        except OSError as e:
            print(f"Error removing existing pipe: {e}")
            sys.exit(1)
    
    # Create a new named pipe
    try:
        os.mkfifo(pipe_path)
        print(f"Created named pipe at {pipe_path}")
    except OSError as e:
        print(f"Error creating named pipe: {e}")
        sys.exit(1)
    
    # Set permissions to allow other processes to read
    os.chmod(pipe_path, 0o666)
    return pipe_path

def find_keyboard_devices():
    """Find all keyboard input devices."""
    devices = []
    try:
        # List input devices from /proc/bus/input/devices
        with open('/proc/bus/input/devices', 'r') as f:
            content = f.read()
        
        # Split by double newline to get each device
        device_blocks = content.split('\n\n')
        
        for block in device_blocks:
            if 'Sycreader' in block or 'RFID' in block or 'keyboard' in block.lower():
                # Extract the device name
                name_match = re.search(r'N: Name="([^"]+)"', block)
                name = name_match.group(1) if name_match else "Unknown"
                
                # Extract the event device handlers
                handlers_match = re.search(r'H: Handlers=([^\n]+)', block)
                if handlers_match:
                    handlers = handlers_match.group(1)
                    # Look for event devices (event0, event1, etc.)
                    event_matches = re.findall(r'(event\d+)', handlers)
                    for event in event_matches:
                        device_path = f"/dev/input/{event}"
                        devices.append((device_path, name))
                        print(f"Found input device: {device_path} ({name})")
        
        if not devices:
            print("No keyboard devices found. Looking for any event device...")
            # Fall back to checking all event devices
            event_devices = [f for f in os.listdir('/dev/input') if f.startswith('event')]
            for event in event_devices:
                device_path = f"/dev/input/{event}"
                devices.append((device_path, "Unknown device"))
                print(f"Found event device: {device_path}")
    
    except Exception as e:
        print(f"Error finding keyboard devices: {e}")
    
    return devices

def handle_exit(signal, frame):
    """Handle exit signals and clean up."""
    print("\nExiting RFID reader...")
    # Clean up pipe on exit
    if os.path.exists("/tmp/rfid_pipe"):
        os.unlink("/tmp/rfid_pipe")
    sys.exit(0)

def read_device(device_path, device_name, pipe_path):
    """Read events from input device and write to pipe."""
    try:
        print(f"Starting to read from device: {device_path} ({device_name})")
        
        # Read raw events from the device
        with open(device_path, 'rb') as device:
            # Buffer to accumulate characters
            buffer = ""
            
            # Simple key code to character mapping for numeric keypad and digits
            # This is a very simplified mapping and might need adjustments
            key_mapping = {
                2: '1', 3: '2', 4: '3', 5: '4', 6: '5',
                7: '6', 8: '7', 9: '8', 10: '9', 11: '0',
                # Add more mappings if needed
            }
            
            while True:
                # Read a raw input event (24 bytes)
                event = device.read(24)
                if not event:
                    continue
                
                # Parse the event
                # Format: struct input_event {
                #     struct timeval time; // 16 bytes
                #     unsigned short type; // 2 bytes
                #     unsigned short code; // 2 bytes
                #     unsigned int value;  // 4 bytes
                # };
                
                # Extract type, code, and value
                event_type = int.from_bytes(event[16:18], byteorder='little')
                event_code = int.from_bytes(event[18:20], byteorder='little')
                event_value = int.from_bytes(event[20:24], byteorder='little')
                
                # Key event (type 1) with key down (value 1)
                if event_type == 1 and event_value == 1:
                    # Enter key (code 28)
                    if event_code == 28:
                        if buffer:
                            # Only process if it looks like an RFID card (all digits)
                            if re.match(r'^\d+$', buffer):
                                with open(pipe_path, 'w') as pipe:
                                    pipe.write(buffer + '\n')
                                print(f"\nRFID scan from {device_name}: {buffer}")
                                print(f"Wrote to pipe: {buffer}")
                            else:
                                print(f"\nIgnored non-RFID input: {buffer}")
                            buffer = ""
                    
                    # Other keys that map to characters
                    elif event_code in key_mapping:
                        char = key_mapping[event_code]
                        buffer += char
                        print(f"{char}", end="", flush=True)
                
    except IOError as e:
        print(f"\nError reading from {device_path}: {e}")
        if e.errno == 13:  # Permission denied
            print(f"Permission denied. Try running the script with sudo.")
    except Exception as e:
        print(f"\nError processing events from {device_path}: {e}")

def main():
    """Main function to read RFID reader input and write to pipe."""
    # Set up exit handler
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    # Create the named pipe
    pipe_path = create_pipe()
    
    # Find keyboard devices
    devices = find_keyboard_devices()
    
    if not devices:
        print("No input devices found. Make sure the RFID reader is connected.")
        if os.path.exists(pipe_path):
            os.unlink(pipe_path)
        return
    
    print("\n=== RFID Reader Started ===")
    print(f"This script will read RFID scans and write them to {pipe_path}")
    print("Present an RFID card to the reader...")
    print("Press Ctrl+C to exit")
    
    # Start a thread for each device
    threads = []
    for device_path, device_name in devices:
        thread = threading.Thread(
            target=read_device, 
            args=(device_path, device_name, pipe_path),
            daemon=True
        )
        threads.append(thread)
        thread.start()
    
    # Wait for threads to finish (which they shouldn't unless there's an error)
    try:
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        print("\nReceived keyboard interrupt, exiting...")
    finally:
        # Clean up on exit
        if os.path.exists(pipe_path):
            os.unlink(pipe_path)
        
        print("RFID reader stopped.")

if __name__ == "__main__":
    main()
