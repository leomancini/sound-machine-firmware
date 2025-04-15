#!/usr/bin/env python3
import os
import time
import signal
import sys
import subprocess
import requests
import json
import threading
import queue
from pathlib import Path
from datetime import datetime

# Configure paths
FIFO_PATH = "/tmp/rfid_audio_pipe"
SOUNDS_BASE_DIR = "/home/fcc-005/sound-machine-firmware/sounds"  # Base directory for sounds
REMOTE_SERVER = "https://labs.noshado.ws/sound-machine-storage"
READY_PIPE = "/tmp/ready_pipe"  # Pipe for sending ready message to visualizer

# Cache for remote file timestamps
remote_timestamps = {}
# Cache for audio file paths
audio_cache = {}
# Flag to track if initial sync has been completed
initial_sync_completed = False
# Queue for audio playback
audio_queue = queue.Queue()
# Flag to control the audio player thread
running = True
# Current audio process
current_audio_process = None

def get_remote_timestamp(url):
    """Get last-modified timestamp of a remote file."""
    if url in remote_timestamps:
        return remote_timestamps[url]
        
    try:
        response = requests.head(url)
        response.raise_for_status()
        if 'last-modified' in response.headers:
            timestamp = response.headers['last-modified']
            remote_timestamps[url] = timestamp
            return timestamp
    except requests.exceptions.RequestException:
        pass
    return None

def get_local_timestamp(file_path):
    """Get last-modified timestamp of a local file."""
    try:
        return datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%a, %d %b %Y %H:%M:%S GMT')
    except (IOError, FileNotFoundError):
        return None

def get_remote_sounds():
    """Get list of all available sounds from the server."""
    try:
        response = requests.get(REMOTE_SERVER)
        response.raise_for_status()
        # Parse the directory listing to get tag IDs
        tag_ids = []
        for line in response.text.split('\n'):
            if '<a href="' in line and '/">' in line:
                tag_id = line.split('<a href="')[1].split('/">')[0]
                # Only include numeric tag IDs that have both required files
                if tag_id.isdigit():
                    # Check if both required files exist
                    try:
                        manifest_url = f"{REMOTE_SERVER}/{tag_id}/manifest.json"
                        audio_url = f"{REMOTE_SERVER}/{tag_id}/audio.mp3"
                        if (requests.head(manifest_url).status_code == 200 and 
                            requests.head(audio_url).status_code == 200):
                            tag_ids.append(tag_id)
                    except requests.exceptions.RequestException:
                        continue
        return tag_ids
    except requests.exceptions.RequestException as e:
        print(f"Error getting remote sounds list: {e}")
        return []

def sync_sounds():
    """Sync local sounds with remote server."""
    global initial_sync_completed
    
    print("Starting sound synchronization...")
    
    # Get list of remote sounds
    remote_sounds = get_remote_sounds()
    if not remote_sounds:
        print("Warning: Could not get list of remote sounds")
        return
    
    print(f"Found {len(remote_sounds)} valid sounds on remote server")
    
    # Get list of local sounds
    local_sounds = []
    try:
        for item in os.listdir(SOUNDS_BASE_DIR):
            if os.path.isdir(os.path.join(SOUNDS_BASE_DIR, item)) and item.isdigit():
                # Only include directories that have both required files
                if (os.path.exists(os.path.join(SOUNDS_BASE_DIR, item, "manifest.json")) and 
                    os.path.exists(os.path.join(SOUNDS_BASE_DIR, item, "audio.mp3"))):
                    local_sounds.append(item)
    except Exception as e:
        print(f"Error getting local sounds list: {e}")
        return
    
    print(f"Found {len(local_sounds)} valid sounds in local cache")
    
    # Delete sounds that no longer exist on the server
    for tag_id in local_sounds:
        if tag_id not in remote_sounds:
            try:
                tag_dir = os.path.join(SOUNDS_BASE_DIR, tag_id)
                print(f"Deleting local sound {tag_id} (no longer on server)")
                subprocess.run(["rm", "-rf", tag_dir], check=True)
            except Exception as e:
                print(f"Error deleting local sound {tag_id}: {e}")
    
    # Download new or changed sounds
    for tag_id in remote_sounds:
        tag_dir = os.path.join(SOUNDS_BASE_DIR, tag_id)
        manifest_path = os.path.join(tag_dir, "manifest.json")
        audio_path = os.path.join(tag_dir, "audio.mp3")
        
        # Check if files exist and compare timestamps
        manifest_url = f"{REMOTE_SERVER}/{tag_id}/manifest.json"
        audio_url = f"{REMOTE_SERVER}/{tag_id}/audio.mp3"
        
        if tag_id not in local_sounds:
            print(f"Downloading new sound {tag_id}")
            download_sound(tag_id)
        else:
            # Check if files have changed using timestamps
            remote_manifest_time = get_remote_timestamp(manifest_url)
            remote_audio_time = get_remote_timestamp(audio_url)
            
            local_manifest_time = get_local_timestamp(manifest_path)
            local_audio_time = get_local_timestamp(audio_path)
            
            if (remote_manifest_time != local_manifest_time or 
                remote_audio_time != local_audio_time):
                print(f"Sound {tag_id} has changed, updating...")
                # Remove existing files before downloading new ones
                try:
                    if os.path.exists(manifest_path):
                        os.remove(manifest_path)
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                except Exception as e:
                    print(f"Error removing old files for {tag_id}: {e}")
                download_sound(tag_id)
    
    print("Sound synchronization complete")
    
    # Build the audio cache after syncing
    build_audio_cache()
    
    # Mark initial sync as completed
    initial_sync_completed = True
    
    # Signal that the system is ready
    signal_ready()

def download_sound(tag_id):
    """Download sound from remote server if not already cached locally."""
    # Create directory for this tag if it doesn't exist
    tag_dir = os.path.join(SOUNDS_BASE_DIR, tag_id)
    os.makedirs(tag_dir, exist_ok=True)
    
    manifest_path = os.path.join(tag_dir, "manifest.json")
    audio_path = os.path.join(tag_dir, "audio.mp3")
    manifest_url = f"{REMOTE_SERVER}/{tag_id}/manifest.json"
    audio_url = f"{REMOTE_SERVER}/{tag_id}/audio.mp3"
    
    # Get remote timestamps
    remote_manifest_time = get_remote_timestamp(manifest_url)
    remote_audio_time = get_remote_timestamp(audio_url)
    
    # Get local timestamps
    local_manifest_time = get_local_timestamp(manifest_path)
    local_audio_time = get_local_timestamp(audio_path)
    
    # Download only changed files
    try:
        # Download manifest if changed or doesn't exist
        if remote_manifest_time != local_manifest_time or not os.path.exists(manifest_path):
            print(f"Updating manifest for {tag_id}")
            response = requests.get(manifest_url)
            response.raise_for_status()
            
            # Save to temporary file first
            temp_manifest = f"{manifest_path}.tmp"
            with open(temp_manifest, 'w') as f:
                f.write(response.text)
            # Atomic rename
            os.rename(temp_manifest, manifest_path)
            
        # Download audio if changed or doesn't exist
        if remote_audio_time != local_audio_time or not os.path.exists(audio_path):
            print(f"Updating audio for {tag_id}")
            response = requests.get(audio_url)
            response.raise_for_status()
            
            # Save to temporary file first
            temp_audio = f"{audio_path}.tmp"
            with open(temp_audio, 'wb') as f:
                f.write(response.content)
            # Atomic rename
            os.rename(temp_audio, audio_path)
            
        print(f"Successfully updated sound for tag {tag_id}")
        return audio_path
        
    except requests.exceptions.RequestException as e:
        print(f"Error downloading sound for tag {tag_id}: {e}")
        # Clean up any temporary files
        for temp_file in [f"{manifest_path}.tmp", f"{audio_path}.tmp"]:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
        return None

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
    global current_audio_process
    
    while running:
        try:
            # Get the next audio file to play (with a timeout)
            audio_path = audio_queue.get(timeout=0.5)
            
            # Kill any currently playing sounds
            if current_audio_process:
                try:
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
            
            # Play the sound using mpg123 with USB Audio device (Card 0)
            try:
                # Use subprocess.Popen instead of os.system for better control
                cmd = ["mpg123", "-a", "hw:0,0", audio_path]
                current_audio_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"Playing audio: {audio_path}")
            except Exception as e:
                print(f"Error playing sound with USB Audio device: {e}")
                try:
                    # Try with alternative syntax for the same device
                    cmd = ["mpg123", "--device", "hw:0,0", audio_path]
                    current_audio_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print(f"Playing audio with alternative command: {audio_path}")
                except Exception as e2:
                    print(f"Alternative also failed: {e2}")
                    current_audio_process = None
            
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
    
    # Check if the audio is in the cache
    if tag_id in audio_cache:
        audio_path = audio_cache[tag_id]
        print(f"Using cached audio for tag {tag_id}: {audio_path}")
    else:
        # If not in cache and initial sync is not completed, download it
        if not initial_sync_completed:
            print(f"Tag {tag_id} not in cache, downloading during initial sync...")
            audio_path = download_sound(tag_id)
            if audio_path:
                # Add to cache for future use
                audio_cache[tag_id] = audio_path
        else:
            print(f"Tag {tag_id} not found in cache and initial sync completed. Skipping.")
            audio_path = None
    
    if not audio_path or not os.path.exists(audio_path):
        print(f"Warning: Could not find audio file for tag {tag_id}")
        return
    
    # Add the audio file to the queue for playback
    audio_queue.put(audio_path)

def cleanup(*args):
    global running
    print("\nShutting down audio player...")
    # Stop the audio player thread
    running = False
    # Kill any active mpg123 processes
    try:
        subprocess.run(["pkill", "mpg123"], check=False)
    except:
        pass
    sys.exit(0)

def main():
    global running
    
    # Set up signal handlers for clean exit
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    # Make sure the pipe exists
    if not os.path.exists(FIFO_PATH):
        os.mkfifo(FIFO_PATH)
        os.chmod(FIFO_PATH, 0o666)
    
    print(f"Audio Player started. Listening for RFID tags from: {FIFO_PATH}")
    print(f"Downloading sounds from: {REMOTE_SERVER}/<tag_id>/audio.mp3")
    print(f"Caching sounds in: {SOUNDS_BASE_DIR}")
    
    # Sync sounds on startup - this will:
    # 1. Get list of all sounds on the server
    # 2. Delete local sounds that no longer exist on the server
    # 3. Download new sounds that don't exist locally
    # 4. Update sounds that have changed on the server
    # 5. Build the audio cache
    sync_sounds()
    
    # Print audio device information
    print("\nDetected audio devices:")
    try:
        subprocess.run(["aplay", "-l"], check=False)
    except:
        print("Could not detect audio devices")
    
    print("\nConfigured to use Card 0: USB Audio device for all playback")
    
    # Start the audio player thread
    audio_thread = threading.Thread(target=audio_player_thread, daemon=True)
    audio_thread.start()
    
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
