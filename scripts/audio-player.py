#!/usr/bin/env python3
import os
import time
import signal
import sys
import subprocess

# Configure paths
FIFO_PATH = "/tmp/rfid_audio_pipe"
SOUNDS_BASE_DIR = "/home/fcc-005/sound-machine-firmware/sounds"  # Base directory for sounds

def play_sound(tag_id):
    # Strip any leading/trailing whitespace from tag_id
    tag_id = tag_id.strip()
    
    print(f"Audio player received tag: {tag_id}")
    
    # Construct the path to the audio file for this tag
    audio_path = os.path.join(SOUNDS_BASE_DIR, tag_id, "audio.mp3")
    
    # Display debug info
    print(f"Looking for audio file: {audio_path}")
    print(f"File exists: {os.path.exists(audio_path)}")
    
    if not os.path.exists(audio_path):
        print(f"Warning: No audio file found for tag {tag_id}")
        return
    
    # Kill any currently playing sounds
    try:
        subprocess.run(["pkill", "mpg123"], check=False)
    except:
        pass
    
    # Play the sound using mpg123 with USB Audio device (Card 0)
    try:
        cmd = f"mpg123 -a hw:0,0 '{audio_path}' &"
        print(f"Running command: {cmd}")
        os.system(cmd)
    except Exception as e:
        print(f"Error playing sound with USB Audio device: {e}")
        try:
            # Try with alternative syntax for the same device
            cmd = f"mpg123 --device hw:0,0 '{audio_path}' &"
            print(f"Trying alternative command: {cmd}")
            os.system(cmd)
        except Exception as e2:
            print(f"Alternative also failed: {e2}")
            # No fallback to default device to ensure we only use USB Audio

def cleanup(*args):
    print("\nShutting down audio player...")
    # Kill any active mpg123 processes
    try:
        subprocess.run(["pkill", "mpg123"], check=False)
    except:
        pass
    sys.exit(0)

def main():
    # Set up signal handlers for clean exit
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    # Make sure the pipe exists
    if not os.path.exists(FIFO_PATH):
        os.mkfifo(FIFO_PATH)
        os.chmod(FIFO_PATH, 0o666)
    
    print(f"Audio Player started. Listening for RFID tags from: {FIFO_PATH}")
    print(f"Looking for audio files in: {SOUNDS_BASE_DIR}/<tag_id>/audio.mp3")
    
    # Display available sound files
    print("Available audio files:")
    try:
        for item in os.listdir(SOUNDS_BASE_DIR):
            if os.path.isdir(os.path.join(SOUNDS_BASE_DIR, item)):
                audio_path = os.path.join(SOUNDS_BASE_DIR, item, "audio.mp3")
                if os.path.exists(audio_path):
                    print(f"  - {item}/audio.mp3 (Found)")
                else:
                    print(f"  - {item}/audio.mp3 (Missing)")
    except Exception as e:
        print(f"Error listing audio files: {e}")
    
    # Print audio device information
    print("\nDetected audio devices:")
    try:
        subprocess.run(["aplay", "-l"], check=False)
    except:
        print("Could not detect audio devices")
    
    print("\nConfigured to use Card 0: USB Audio device for all playback")
    
    # Test the audio device
#    print("Testing USB Audio device...")
#    test_cmd = "speaker-test -D plughw:0,0 -c 2 -t sine -f 440 -l 1 >/dev/null 2>&1"
#    test_result = os.system(test_cmd)
#    if test_result == 0:
#        print("USB Audio device test successful")
#    else:
#        print("Warning: USB Audio device test failed, but will try to use it anyway")
    
    # Main loop - continuously read from the pipe
    while True:
        try:
            # Open the pipe for reading (blocks until data is available)
            with open(FIFO_PATH, 'r') as fifo:
                # Read from the pipe
                tag_id = fifo.readline().strip()
                if tag_id:
                    play_sound(tag_id)
        except Exception as e:
            print(f"Error reading from pipe: {e}")
            time.sleep(1)  # Wait before trying to reopen the pipe

if __name__ == "__main__":
    main()
