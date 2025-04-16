#!/usr/bin/env python3
import os
import time
import signal
import sys
import subprocess
import threading
import queue
import hashlib
from pathlib import Path
from datetime import datetime
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure paths
FIFO_PATH = "/tmp/rfid_audio_pipe"
SOUNDS_BASE_DIR = "/home/fcc-005/sound-machine-firmware/sounds"  # Base directory for sounds
READY_PIPE = "/tmp/ready_pipe"  # Pipe for sending ready message to visualizer

# Cache for audio file paths
audio_cache = {}
# Queue for audio playback
audio_queue = queue.Queue()
# Flag to control the audio player thread
running = True
# Current audio process
current_audio_process = None
# Flag to track if we're stopping for a new tag
stopping_for_new_tag = False

def build_audio_cache():
    """Build a cache of all available audio files."""
    global audio_cache
    audio_cache = {}
    
    print("Building audio cache...")
    try:
        for item in os.listdir(SOUNDS_BASE_DIR):
            if os.path.isdir(os.path.join(SOUNDS_BASE_DIR, item)) and item.isdigit():
                audio_path = os.path.join(SOUNDS_BASE_DIR, item, "audio.mp3")
                if os.path.exists(audio_path):
                    audio_cache[item] = audio_path
                    print(f"Cached audio for tag {item}: {audio_path}")
    except Exception as e:
        print(f"Error building audio cache: {e}")
    
    print(f"Audio cache built with {len(audio_cache)} entries")

def signal_ready():
    """Signal that the system is ready by sending a message to the visualizer."""
    print("System is ready! Signaling to visualizer...")
    
    # Create the ready pipe if it doesn't exist
    if not os.path.exists(READY_PIPE):
        os.mkfifo(READY_PIPE)
        os.chmod(READY_PIPE, 0o666)
    
    # Send the ready message to the visualizer
    try:
        with open(READY_PIPE, 'w') as pipe:
            pipe.write("READY\n")
            pipe.flush()
        print("Ready signal sent to visualizer")
    except Exception as e:
        print(f"Error sending ready signal: {e}")

def audio_player_thread():
    """Thread function to handle audio playback."""
    global current_audio_process, stopping_for_new_tag
    
    while running:
        try:
            # Get the next audio file from the queue
            audio_path = audio_queue.get()
            if audio_path is None:
                break
                
            # Play the sound using mpg123 with USB Audio device (Card 0)
            try:
                # Use subprocess.Popen instead of os.system for better control
                cmd = ["mpg123", "-a", "hw:0,0", audio_path]
                current_audio_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"Playing audio: {audio_path}")
                
                # Wait for the audio to finish playing
                current_audio_process.wait()
                
                # Only signal ready if we're not stopping for a new tag
                if not stopping_for_new_tag:
                    signal_ready()
                    print("Audio finished playing naturally, sent READY signal")
                
            except Exception as e:
                print(f"Error playing sound with USB Audio device: {e}")
                try:
                    # Try with alternative syntax for the same device
                    cmd = ["mpg123", "--device", "hw:0,0", audio_path]
                    current_audio_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print(f"Playing audio with alternative command: {audio_path}")
                    
                    # Wait for the audio to finish playing
                    current_audio_process.wait()
                    
                    # Only signal ready if we're not stopping for a new tag
                    if not stopping_for_new_tag:
                        signal_ready()
                        print("Audio finished playing naturally, sent READY signal")
                    
                except Exception as e2:
                    print(f"Alternative also failed: {e2}")
                    current_audio_process = None
                    
                    # Only send READY signal if we completely failed to play any audio and not stopping for new tag
                    if (not current_audio_process or current_audio_process.poll() is not None) and not stopping_for_new_tag:
                        signal_ready()
                        print("Audio failed to play, sent READY signal")
            
            # Mark the task as done
            audio_queue.task_done()
            
        except queue.Empty:
            # No audio to play, just continue
            pass
        except Exception as e:
            print(f"Error in audio player thread: {e}")
            time.sleep(0.1)  # Short sleep to prevent CPU spinning

def play_sound(tag_id):
    # Strip any leading/trailing whitespace from tag_id
    tag_id = tag_id.strip()
    
    print(f"Audio player received tag: {tag_id}")
    
    # Kill any currently playing sounds immediately
    global current_audio_process, stopping_for_new_tag
    if current_audio_process:
        try:
            print("Stopping current audio to play new tag")
            stopping_for_new_tag = True  # Set flag before stopping
            current_audio_process.terminate()
            current_audio_process.wait(timeout=1)
        except:
            # If termination fails, force kill
            try:
                current_audio_process.kill()
            except:
                pass
            # Also try to kill any remaining mpg123 processes
            subprocess.run(["pkill", "mpg123"], check=False)
        
        # Send READY signal when stopping for a new tag
        signal_ready()
        print("Audio stopped for new tag, sent READY signal")
        stopping_for_new_tag = False  # Reset flag after sending signal
    
    # Check if the audio is in the cache
    if tag_id in audio_cache:
        audio_path = audio_cache[tag_id]
        print(f"Using cached audio for tag {tag_id}: {audio_path}")
    else:
        # By default, don't download sounds that aren't in the cache
        print(f"Tag {tag_id} not found in cache. Skipping.")
        audio_path = None
    
    if not audio_path or not os.path.exists(audio_path):
        print(f"Warning: Could not find audio file for tag {tag_id}")
        return
    
    # Add the audio file to the queue for playback
    audio_queue.put(audio_path)

def cleanup(*args):
    """Clean up resources before exiting."""
    global running, current_audio_process
    
    print("Cleaning up...")
    running = False
    
    # Stop the current audio process if it's running
    if current_audio_process and current_audio_process.poll() is None:
        print("Stopping current audio process...")
        current_audio_process.terminate()
        try:
            current_audio_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            print("Audio process did not terminate, killing...")
            current_audio_process.kill()
    
    print("Cleanup complete")
    sys.exit(0)

def main():
    global running
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Audio player for sound machine')
    parser.add_argument('--force-update', action='store_true', help='Force update all sounds regardless of timestamps')
    parser.add_argument('--sync-interval', type=int, default=300, help='Interval in seconds for periodic sync (default: 300)')
    parser.add_argument('--max-downloads', type=int, default=5, help='Maximum number of concurrent downloads (default: 5)')
    parser.add_argument('--resync', action='store_true', help='Perform a full resync on startup')
    args = parser.parse_args()

    
    # Set up signal handlers for clean exit
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    # Make sure the pipe exists
    if not os.path.exists(FIFO_PATH):
        os.mkfifo(FIFO_PATH)
        os.chmod(FIFO_PATH, 0o666)
    
    print(f"Audio Player started. Listening for RFID tags from: {FIFO_PATH}")
    print(f"Caching sounds in: {SOUNDS_BASE_DIR}")
    
    # Start the audio player thread immediately
    audio_thread = threading.Thread(target=audio_player_thread, daemon=True)
    audio_thread.start()
    
    # Build the audio cache from existing files
    build_audio_cache()
    # Signal that the system is ready
    signal_ready()
    
    # Print audio device information
    print("\nDetected audio devices:")
    try:
        subprocess.run(["aplay", "-l"], check=False)
    except:
        print("Could not detect audio devices")
    
    print("\nConfigured to use Card 0: USB Audio device for all playback")
    
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
