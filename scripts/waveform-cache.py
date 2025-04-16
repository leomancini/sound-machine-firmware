#!/usr/bin/env python3
import os
import json
import threading
import time

class WaveformCache:
    def __init__(self, sounds_base_dir="/home/fcc-005/sound-machine-firmware/sounds"):
        self.sounds_base_dir = sounds_base_dir
        self.cache = {}
        self.lock = threading.Lock()
        self.cache_loaded = False
        
    def build_cache(self):
        """Build a cache of all available waveform files."""
        with self.lock:
            if self.cache_loaded:
                return
                
            print("Building waveform cache...")
            try:
                for item in os.listdir(self.sounds_base_dir):
                    if os.path.isdir(os.path.join(self.sounds_base_dir, item)) and item.isdigit():
                        waveform_path = os.path.join(self.sounds_base_dir, item, "waveform.json")
                        if os.path.exists(waveform_path):
                            try:
                                with open(waveform_path, 'r') as f:
                                    waveform_data = json.load(f)
                                    self.cache[item] = waveform_data
                                    print(f"Cached waveform for tag {item}")
                            except Exception as e:
                                print(f"Error loading waveform for tag {item}: {e}")
            except Exception as e:
                print(f"Error building waveform cache: {e}")
            
            self.cache_loaded = True
            print(f"Waveform cache built with {len(self.cache)} entries")
    
    def get_waveform(self, tag_id):
        """Get waveform data for a specific tag ID."""
        with self.lock:
            if not self.cache_loaded:
                self.build_cache()
            
            # Strip any leading/trailing whitespace from tag_id
            tag_id = tag_id.strip()
            
            if tag_id in self.cache:
                return self.cache[tag_id]
            
            # If not in cache, try to load it directly
            waveform_path = os.path.join(self.sounds_base_dir, tag_id, "waveform.json")
            if os.path.exists(waveform_path):
                try:
                    with open(waveform_path, 'r') as f:
                        waveform_data = json.load(f)
                        self.cache[tag_id] = waveform_data
                        return waveform_data
                except Exception as e:
                    print(f"Error loading waveform for tag {tag_id}: {e}")
            
            return None
    
    def clear_cache(self):
        """Clear the waveform cache."""
        with self.lock:
            self.cache.clear()
            self.cache_loaded = False
            print("Waveform cache cleared")

# Create a global instance
waveform_cache = WaveformCache() 