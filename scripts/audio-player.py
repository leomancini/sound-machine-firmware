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
import argparse

# Configure paths
FIFO_PATH = "/tmp/rfid_audio_pipe"
SOUNDS_BASE_DIR = "/home/fcc-005/sound-machine-firmware/sounds"  # Base directory for sounds
REMOTE_SERVER = "https://labs.noshado.ws/sound-machine-storage"
READY_PIPE = "/tmp/ready_pipe"  # Pipe for sending ready message to visualizer
PROGRESS_PIPE = "/tmp/progress_pipe"  # Pipe for sending progress updates to visualizer

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
# Flag to control the periodic sync thread
periodic_sync_running = True
# Interval for periodic sync (in seconds)
PERIODIC_SYNC_INTERVAL = 300  # 5 minutes

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

def send_progress(progress, message):
    """Send progress update to the visualizer."""
    try:
        # Create the progress pipe if it doesn't exist
        if not os.path.exists(PROGRESS_PIPE):
            os.mkfifo(PROGRESS_PIPE)
            os.chmod(PROGRESS_PIPE, 0o666)
        
        # Send the progress message
        with open(PROGRESS_PIPE, 'w') as pipe:
            pipe.write(f"{progress},{message}\n")
            pipe.flush()
        print(f"Progress: {progress}% - {message}")
    except Exception as e:
        print(f"Error sending progress update: {e}")

def sync_sounds(force_update=False):
    """Sync local sounds with remote server."""
    global initial_sync_completed
    
    print("Starting sound synchronization...")
    if force_update:
        print("FORCE UPDATE MODE: Will update all sounds regardless of timestamps")
    send_progress(0, "Starting sound synchronization")
    
    # Get list of remote sounds
    send_progress(5, "Getting list of remote sounds")
    remote_sounds = get_remote_sounds()
    if not remote_sounds:
        print("Warning: Could not get list of remote sounds")
        send_progress(100, "Error: Could not get list of remote sounds")
        return
    
    print(f"Found {len(remote_sounds)} valid sounds on remote server")
    send_progress(10, f"Found {len(remote_sounds)} sounds on server")
    
    # Get list of local sounds
    send_progress(15, "Checking local sounds")
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
        send_progress(100, f"Error: {str(e)}")
        return
    
    print(f"Found {len(local_sounds)} valid sounds in local cache")
    send_progress(20, f"Found {len(local_sounds)} local sounds")
    
    # Delete sounds that no longer exist on the server
    send_progress(25, "Checking for deleted sounds")
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
    
    if deleted_count > 0:
        send_progress(30, f"Deleted {deleted_count} old sounds")
    
    # Download new or changed sounds
    send_progress(35, "Checking for new or updated sounds")
    total_sounds = len(remote_sounds)
    processed_sounds = 0
    new_sounds = 0
    updated_sounds = 0
    
    for tag_id in remote_sounds:
        tag_dir = os.path.join(SOUNDS_BASE_DIR, tag_id)
        manifest_path = os.path.join(tag_dir, "manifest.json")
        audio_path = os.path.join(tag_dir, "audio.mp3")
        
        # Check if files exist and compare timestamps
        manifest_url = f"{REMOTE_SERVER}/{tag_id}/manifest.json"
        audio_url = f"{REMOTE_SERVER}/{tag_id}/audio.mp3"
        
        if tag_id not in local_sounds:
            print(f"Downloading new sound {tag_id}")
            send_progress(35 + int(processed_sounds / total_sounds * 50), 
                         f"Downloading new sound {tag_id}")
            download_sound(tag_id)
            new_sounds += 1
        else:
            # Check if files have changed using timestamps
            remote_manifest_time = get_remote_timestamp(manifest_url)
            remote_audio_time = get_remote_timestamp(audio_url)
            
            local_manifest_time = get_local_timestamp(manifest_path)
            local_audio_time = get_local_timestamp(audio_path)
            
            # Check if files are actually different by comparing content
            manifest_changed = False
            audio_changed = False
            
            # For manifest, compare the actual content
            if os.path.exists(manifest_path):
                try:
                    # Parse local manifest as JSON
                    with open(manifest_path, 'r') as f:
                        local_manifest_content = f.read().strip()
                        try:
                            local_manifest_json = json.loads(local_manifest_content)
                        except json.JSONDecodeError as e:
                            print(f"Error parsing local manifest JSON for {tag_id}: {e}")
                            local_manifest_json = None
                    
                    # Parse remote manifest as JSON
                    response = requests.get(manifest_url)
                    response.raise_for_status()
                    remote_manifest_content = response.text.strip()
                    try:
                        remote_manifest_json = json.loads(remote_manifest_content)
                    except json.JSONDecodeError as e:
                        print(f"Error parsing remote manifest JSON for {tag_id}: {e}")
                        remote_manifest_json = None
                    
                    # Compare JSON objects if both were successfully parsed
                    if local_manifest_json is not None and remote_manifest_json is not None:
                        # Compare the actual data values
                        if local_manifest_json != remote_manifest_json:
                            manifest_changed = True
                            print(f"Manifest content changed for {tag_id}")
                            print(f"  Local: {json.dumps(local_manifest_json)}")
                            print(f"  Remote: {json.dumps(remote_manifest_json)}")
                        else:
                            print(f"Manifest content is identical for {tag_id}")
                    else:
                        # If JSON parsing failed, fall back to string comparison
                        if local_manifest_content != remote_manifest_content:
                            manifest_changed = True
                            print(f"Manifest content changed for {tag_id} (string comparison)")
                            print(f"  Local: {local_manifest_content}")
                            print(f"  Remote: {remote_manifest_content}")
                except Exception as e:
                    print(f"Error comparing manifest content for {tag_id}: {e}")
                    # If we can't compare content, fall back to timestamp comparison
                    manifest_changed = (remote_manifest_time != local_manifest_time)
            else:
                manifest_changed = True
            
            # For audio, compare file sizes as a quick check
            if os.path.exists(audio_path):
                try:
                    local_audio_size = os.path.getsize(audio_path)
                    response = requests.head(audio_url)
                    response.raise_for_status()
                    remote_audio_size = int(response.headers.get('content-length', 0))
                    
                    if local_audio_size != remote_audio_size:
                        audio_changed = True
                        print(f"Audio file size changed for {tag_id}: local={local_audio_size}, remote={remote_audio_size}")
                except Exception as e:
                    print(f"Error comparing audio size for {tag_id}: {e}")
                    # If we can't compare size, fall back to timestamp comparison
                    audio_changed = (remote_audio_time != local_audio_time)
            else:
                audio_changed = True
            
            # If force update is enabled, always update
            if force_update:
                manifest_changed = True
                audio_changed = True
                print(f"Force update enabled for {tag_id}")
            
            if manifest_changed or audio_changed:
                print(f"Sound {tag_id} has changed, updating...")
                send_progress(35 + int(processed_sounds / total_sounds * 50), 
                             f"Updating sound {tag_id}")
                # Remove existing files before downloading new ones
                try:
                    if os.path.exists(manifest_path):
                        os.remove(manifest_path)
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                except Exception as e:
                    print(f"Error removing old files for {tag_id}: {e}")
                download_sound(tag_id)
                updated_sounds += 1
            else:
                send_progress(35 + int(processed_sounds / total_sounds * 50), 
                             f"Sound {tag_id} is up to date")
        
        processed_sounds += 1
    
    print("Sound synchronization complete")
    send_progress(85, "Sound synchronization complete")
    
    # Build the audio cache after syncing
    send_progress(90, "Building audio cache")
    build_audio_cache()
    
    # Mark initial sync as completed
    initial_sync_completed = True
    
    # Signal that the system is ready
    send_progress(100, "System ready")
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
    
    print(f"Downloading sound for tag {tag_id}")
    print(f"  - Manifest URL: {manifest_url}")
    print(f"  - Audio URL: {audio_url}")
    print(f"  - Local manifest path: {manifest_path}")
    print(f"  - Local audio path: {audio_path}")
    
    # Get remote timestamps
    remote_manifest_time = get_remote_timestamp(manifest_url)
    remote_audio_time = get_remote_timestamp(audio_url)
    
    print(f"  - Remote manifest timestamp: {remote_manifest_time}")
    print(f"  - Remote audio timestamp: {remote_audio_time}")
    
    # Get local timestamps
    local_manifest_time = get_local_timestamp(manifest_path)
    local_audio_time = get_local_timestamp(audio_path)
    
    print(f"  - Local manifest timestamp: {local_manifest_time}")
    print(f"  - Local audio timestamp: {local_audio_time}")
    
    # Download only changed files
    try:
        # Download manifest if changed or doesn't exist
        if remote_manifest_time != local_manifest_time or not os.path.exists(manifest_path):
            print(f"  - Updating manifest for {tag_id}")
            response = requests.get(manifest_url)
            response.raise_for_status()
            
            # Save to temporary file first
            temp_manifest = f"{manifest_path}.tmp"
            with open(temp_manifest, 'w') as f:
                f.write(response.text)
            
            # Verify the temp file was created and has content
            if not os.path.exists(temp_manifest):
                raise Exception(f"Failed to create temporary manifest file: {temp_manifest}")
            
            temp_size = os.path.getsize(temp_manifest)
            if temp_size == 0:
                raise Exception(f"Temporary manifest file is empty: {temp_manifest}")
            
            print(f"  - Temporary manifest file created: {temp_manifest} ({temp_size} bytes)")
            
            # Atomic rename
            os.rename(temp_manifest, manifest_path)
            
            # Verify the file was renamed successfully
            if not os.path.exists(manifest_path):
                raise Exception(f"Failed to rename manifest file: {manifest_path}")
            
            print(f"  - Manifest file saved: {manifest_path}")
        else:
            print(f"  - Manifest file is up to date: {manifest_path}")
            
        # Download audio if changed or doesn't exist
        if remote_audio_time != local_audio_time or not os.path.exists(audio_path):
            print(f"  - Updating audio for {tag_id}")
            response = requests.get(audio_url)
            response.raise_for_status()
            
            # Save to temporary file first
            temp_audio = f"{audio_path}.tmp"
            with open(temp_audio, 'wb') as f:
                f.write(response.content)
            
            # Verify the temp file was created and has content
            if not os.path.exists(temp_audio):
                raise Exception(f"Failed to create temporary audio file: {temp_audio}")
            
            temp_size = os.path.getsize(temp_audio)
            if temp_size == 0:
                raise Exception(f"Temporary audio file is empty: {temp_audio}")
            
            print(f"  - Temporary audio file created: {temp_audio} ({temp_size} bytes)")
            
            # Atomic rename
            os.rename(temp_audio, audio_path)
            
            # Verify the file was renamed successfully
            if not os.path.exists(audio_path):
                raise Exception(f"Failed to rename audio file: {audio_path}")
            
            print(f"  - Audio file saved: {audio_path}")
        else:
            print(f"  - Audio file is up to date: {audio_path}")
            
        # Final verification that both files exist
        if not os.path.exists(manifest_path):
            raise Exception(f"Manifest file does not exist after download: {manifest_path}")
        
        if not os.path.exists(audio_path):
            raise Exception(f"Audio file does not exist after download: {audio_path}")
        
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
    except Exception as e:
        print(f"Error processing sound for tag {tag_id}: {e}")
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
            # Run sync without force update
            sync_sounds(force_update=False)
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
    args = parser.parse_args()
    
    # Set the sync interval from command line args
    global PERIODIC_SYNC_INTERVAL
    PERIODIC_SYNC_INTERVAL = args.sync_interval
    
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
    
    # Sync sounds on startup - this will:
    # 1. Get list of all sounds on the server
    # 2. Delete local sounds that no longer exist on the server
    # 3. Download new sounds that don't exist locally
    # 4. Update sounds that have changed on the server
    # 5. Build the audio cache
    sync_sounds(force_update=args.force_update)
    
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
    
    # Start the periodic sync thread
    sync_thread = threading.Thread(target=periodic_sync_thread, daemon=True)
    sync_thread.start()
    
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
