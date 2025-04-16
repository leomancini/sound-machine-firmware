#!/usr/bin/env python3
import os
import time
import requests
import json
import hashlib
from pathlib import Path
from datetime import datetime
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure paths
SOUNDS_BASE_DIR = "/home/fcc-005/sound-machine-firmware/sounds"  # Base directory for sounds
REMOTE_SERVER = "https://labs.noshado.ws/sound-machine-storage"

# Cache for remote file timestamps and hashes
remote_timestamps = {}
remote_hashes = {}

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

def get_remote_hash(url):
    """Get MD5 hash of a remote file."""
    if url in remote_hashes:
        return remote_hashes[url]
        
    try:
        response = requests.get(url)
        response.raise_for_status()
        file_hash = hashlib.md5(response.content).hexdigest()
        remote_hashes[url] = file_hash
        return file_hash
    except requests.exceptions.RequestException:
        pass
    return None

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
                        # Print progress
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            print(f"\rDownloading {os.path.basename(local_path)}: {progress:.1f}%", end='')
        
        print()  # New line after progress
        
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
        remote_manifest_hash = get_remote_hash(manifest_url)
        local_manifest_hash = get_local_hash(manifest_path)
        if remote_manifest_hash and local_manifest_hash and remote_manifest_hash == local_manifest_hash:
            manifest_needs_update = False
    
    # Check audio
    if os.path.exists(audio_path):
        remote_audio_hash = get_remote_hash(audio_url)
        local_audio_hash = get_local_hash(audio_path)
        if remote_audio_hash and local_audio_hash and remote_audio_hash == local_audio_hash:
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

def sync_sounds(force_update=False):
    """Sync local sounds with remote server."""
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
                os.system(f"rm -rf {tag_dir}")
                deleted_count += 1
            except Exception as e:
                print(f"Error deleting local sound {tag_id}: {e}")
    
    # Download new or changed sounds
    total_sounds = len(remote_sounds)
    processed_sounds = 0
    new_sounds = 0
    updated_sounds = 0
    
    # Process sounds in parallel batches
    with ThreadPoolExecutor(max_workers=5) as executor:
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
                    remote_manifest_hash = get_remote_hash(manifest_url)
                    local_manifest_hash = get_local_hash(manifest_path)
                    if remote_manifest_hash and local_manifest_hash and remote_manifest_hash == local_manifest_hash:
                        manifest_needs_update = False
                
                # Check audio
                if os.path.exists(audio_path):
                    remote_audio_hash = get_remote_hash(audio_url)
                    local_audio_hash = get_local_hash(audio_path)
                    if remote_audio_hash and local_audio_hash and remote_audio_hash == local_audio_hash:
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
    
    print("\nSound synchronization complete")
    print(f"Deleted {deleted_count} sounds")
    print(f"Added {new_sounds} new sounds")
    print(f"Updated {updated_sounds} existing sounds")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Resync sounds with remote server')
    parser.add_argument('--force', action='store_true', help='Force update all sounds regardless of timestamps')
    args = parser.parse_args()
    
    # Run the sync
    sync_sounds(force_update=args.force)

if __name__ == "__main__":
    main() 