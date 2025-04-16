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
import hashlib
from pathlib import Path
from datetime import datetime
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure paths
FIFO_PATH = "/tmp/rfid_audio_pipe"
SOUNDS_BASE_DIR = "/home/fcc-005/sound-machine-firmware/sounds"  # Base directory for sounds
REMOTE_SERVER = "https://labs.noshado.ws/sound-machine-storage"
READY_PIPE = "/tmp/ready_pipe"  # Pipe for sending ready message to visualizer

# Cache for remote file timestamps and hashes
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
# Flag to control the periodic sync thread
periodic_sync_running = True
# Interval for periodic sync (in seconds)
PERIODIC_SYNC_INTERVAL = 300  # 5 minutes
# Maximum number of concurrent downloads
MAX_CONCURRENT_DOWNLOADS = 5
# Flag to track if we're stopping for a new tag
stopping_for_new_tag = False

def get_local_hash(file_path):
    """Get MD5 hash of a local file."""
    try:
        if not os.path.exists(file_path):
            return None
        with open(file_path, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()
    except (IOError, FileNotFoundError):
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

def send_progress(progress, message):
    """Send progress update to the visualizer."""
    # This function is no longer needed since we removed the progress bar
    print(f"Progress: {progress}% - {message}")

def download_file(url, local_path):
    """Download a file from URL to local path with atomic write."""
    try:
        # Create temporary file path
        temp_path = f"{local_path}.tmp"
        
        # Download to temporary file
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        # Get file size for progress tracking
        total_size = int(response.headers.get('content-length', 0))
        
        # Write to temporary file
        with open(temp_path, 'wb') as f:
            if total_size == 0:
                f.write(response.content)
            else:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
        
        # Verify the temp file was created and has content
        if not os.path.exists(temp_path):
            raise Exception(f"Failed to create temporary file: {temp_path}")
        
        temp_size = os.path.getsize(temp_path)
        if temp_size == 0:
            raise Exception(f"Temporary file is empty: {temp_path}")
        
        # Atomic rename
        os.rename(temp_path, local_path)
        
        # Verify the file was renamed successfully
        if not os.path.exists(local_path):
            raise Exception(f"Failed to rename file: {local_path}")
        
        return True
    except Exception as e:
        print(f"Error downloading file {url} to {local_path}: {e}")
        # Clean up temporary file if it exists
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        return False

def download_sound_parallel(tag_id):
    """Download sound files in parallel."""
    tag_dir = os.path.join(SOUNDS_BASE_DIR, tag_id)
    os.makedirs(tag_dir, exist_ok=True)
    
    manifest_path = os.path.join(tag_dir, "manifest.json")
    audio_path = os.path.join(tag_dir, "audio.mp3")
    manifest_url = f"{REMOTE_SERVER}/{tag_id}/manifest.json"
    audio_url = f"{REMOTE_SERVER}/{tag_id}/audio.mp3"
    
    # Check if files need to be updated using hash comparison
    manifest_needs_update = True
    audio_needs_update = True
    
    # Check manifest
    if os.path.exists(manifest_path):
        manifest_needs_update = False
    
    # Check audio
    if os.path.exists(audio_path):
        audio_needs_update = False
    
    # Download files in parallel if needed
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = []
        
        if manifest_needs_update:
            futures.append(executor.submit(download_file, manifest_url, manifest_path))
        
        if audio_needs_update:
            futures.append(executor.submit(download_file, audio_url, audio_path))
        
        # Wait for all downloads to complete
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"Error in parallel download for {tag_id}: {e}")
    
    # Verify both files exist
    if os.path.exists(manifest_path) and os.path.exists(audio_path):
        return audio_path
    else:
        return None

def sync_sounds(force_update=False, is_initial_sync=False):
    """Sync local sounds with remote server."""
    global initial_sync_completed
    
    print("Starting sound synchronization...")
    if force_update:
        print("FORCE UPDATE MODE: Will update all sounds regardless of timestamps")
    
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
    deleted_count = 0
    for tag_id in local_sounds:
        if tag_id not in remote_sounds:
            try:
                tag_dir = os.path.join(SOUNDS_BASE_DIR, tag_id)
                print(f"Deleting local sound {tag_id} (no longer on server)")
                subprocess.run(["rm", "-rf", tag_dir], check=True)
                deleted_count += 1
            except Exception as e:
                print(f"Error deleting local sound {tag_id}: {e}")
    
    # Download new or changed sounds
    total_sounds = len(remote_sounds)
    processed_sounds = 0
    new_sounds = 0
    updated_sounds = 0
    
    # Process sounds in parallel batches
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_DOWNLOADS) as executor:
        futures = {}
        
        for tag_id in remote_sounds:
            tag_dir = os.path.join(SOUNDS_BASE_DIR, tag_id)
            manifest_path = os.path.join(tag_dir, "manifest.json")
            audio_path = os.path.join(tag_dir, "audio.mp3")
            
            # Check if files exist and compare hashes
            manifest_url = f"{REMOTE_SERVER}/{tag_id}/manifest.json"
            audio_url = f"{REMOTE_SERVER}/{tag_id}/audio.mp3"
            
            if tag_id not in local_sounds:
                print(f"Downloading new sound {tag_id}")
                futures[executor.submit(download_sound_parallel, tag_id)] = tag_id
                new_sounds += 1
            else:
                # Check if files have changed using hash comparison
                manifest_needs_update = True
                audio_needs_update = True
                
                # Check manifest
                if os.path.exists(manifest_path):
                    manifest_needs_update = False
                
                # Check audio
                if os.path.exists(audio_path):
                    audio_needs_update = False
                
                # If force update is enabled, always update
                if force_update:
                    manifest_needs_update = True
                    audio_needs_update = True
                
                if manifest_needs_update or audio_needs_update:
                    print(f"Sound {tag_id} has changed, updating...")
                    futures[executor.submit(download_sound_parallel, tag_id)] = tag_id
                    updated_sounds += 1
                else:
                    print(f"Sound {tag_id} is up to date")
            
            processed_sounds += 1
        
        # Wait for all downloads to complete
        for future in as_completed(futures):
            tag_id = futures[future]
            try:
                result = future.result()
                if result:
                    print(f"Successfully updated sound for tag {tag_id}")
                else:
                    print(f"Failed to update sound for tag {tag_id}")
            except Exception as e:
                print(f"Error updating sound for tag {tag_id}: {e}")
    
    print("Sound synchronization complete")
    
    # Build the audio cache after syncing
    build_audio_cache()
    
    # Mark initial sync as completed
    initial_sync_completed = True
    
    # Signal that the system is ready
    signal_ready()

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
        # If not in cache and initial sync is not completed, download it
        if not initial_sync_completed:
            print(f"Tag {tag_id} not in cache, downloading during initial sync...")
            audio_path = download_sound_parallel(tag_id)
            if audio_path:
                # Add to cache for future use
                audio_cache[tag_id] = audio_path
                print(f"Successfully downloaded sound for tag {tag_id}")
            else:
                print(f"Failed to download sound for tag {tag_id}")
        else:
            print(f"Tag {tag_id} not found in cache and initial sync completed. Skipping.")
            audio_path = None
    
    if not audio_path or not os.path.exists(audio_path):
        print(f"Warning: Could not find audio file for tag {tag_id}")
        return
    
    # Add the audio file to the queue for playback
    audio_queue.put(audio_path)

def periodic_sync_thread():
    """Thread function to periodically sync sounds with the server."""
    global periodic_sync_running
    
    print("Starting periodic sync thread")
    while periodic_sync_running:
        try:
            # Sleep for the specified interval
            time.sleep(PERIODIC_SYNC_INTERVAL)
            
            # Check if we should still be running
            if not periodic_sync_running:
                break
                
            print("Running periodic sync...")
            # Run sync without force update and without detailed progress updates
            sync_sounds(force_update=False, is_initial_sync=False)
        except Exception as e:
            print(f"Error in periodic sync thread: {e}")
            # Sleep for a bit before retrying
            time.sleep(60)
    
    print("Periodic sync thread stopped")

def cleanup(*args):
    """Clean up resources before exiting."""
    global running, periodic_sync_running, current_audio_process
    
    print("Cleaning up...")
    running = False
    periodic_sync_running = False
    
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
    global running, periodic_sync_running
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Audio player for sound machine')
    parser.add_argument('--force-update', action='store_true', help='Force update all sounds regardless of timestamps')
    parser.add_argument('--sync-interval', type=int, default=300, help='Interval in seconds for periodic sync (default: 300)')
    parser.add_argument('--max-downloads', type=int, default=5, help='Maximum number of concurrent downloads (default: 5)')
    parser.add_argument('--resync', action='store_true', help='Perform a full resync on startup')
    args = parser.parse_args()
    
    # Set the sync interval from command line args
    global PERIODIC_SYNC_INTERVAL, MAX_CONCURRENT_DOWNLOADS
    PERIODIC_SYNC_INTERVAL = args.sync_interval
    MAX_CONCURRENT_DOWNLOADS = args.max_downloads
    
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
    print(f"Periodic sync interval: {PERIODIC_SYNC_INTERVAL} seconds")
    print(f"Maximum concurrent downloads: {MAX_CONCURRENT_DOWNLOADS}")
    
    # Start the audio player thread immediately
    audio_thread = threading.Thread(target=audio_player_thread, daemon=True)
    audio_thread.start()
    
    # Start the periodic sync thread
    sync_thread = threading.Thread(target=periodic_sync_thread, daemon=True)
    sync_thread.start()
    
    # Only sync sounds on startup if --resync flag is provided
    if args.resync:
        print("Performing full resync on startup...")
        sync_thread = threading.Thread(target=lambda: sync_sounds(force_update=args.force_update, is_initial_sync=True), daemon=True)
        sync_thread.start()
    else:
        print("Skipping initial sync. Using existing sounds on device.")
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
