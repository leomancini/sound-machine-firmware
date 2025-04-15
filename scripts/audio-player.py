#!/usr/bin/env python3
import os
import time
import signal
import sys
import subprocess
import requests
import json
from pathlib import Path
from datetime import datetime

# Configure paths
FIFO_PATH = "/tmp/rfid_audio_pipe"
SOUNDS_BASE_DIR = "/home/fcc-005/sound-machine-firmware/sounds"  # Base directory for sounds
REMOTE_SERVER = "https://labs.noshado.ws/sound-machine-storage"

# Cache for remote file timestamps
remote_timestamps = {}

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
                download_sound(tag_id)
    
    print("Sound synchronization complete")

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

def play_sound(tag_id):
    # Strip any leading/trailing whitespace from tag_id
    tag_id = tag_id.strip()
    
    print(f"Audio player received tag: {tag_id}")
    
    # Download or get cached audio file
    audio_path = download_sound(tag_id)
    
    if not audio_path:
        print(f"Warning: Could not download audio file for tag {tag_id}")
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
    print(f"Downloading sounds from: {REMOTE_SERVER}/<tag_id>/audio.mp3")
    print(f"Caching sounds in: {SOUNDS_BASE_DIR}")
    
    # Sync sounds on startup
    sync_sounds()
    
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
