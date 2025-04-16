#!/usr/bin/env python3
from samplebase import SampleBase
import math
import random
import threading
import time
import os
import json

SOUNDS_BASE_DIR = "/home/fcc-005/sound-machine-firmware/sounds"  # Base directory for sounds

class WaveformAnimation(SampleBase):
    def __init__(self, *args, **kwargs):
        super(WaveformAnimation, self).__init__(*args, **kwargs)
        self.lock = threading.Lock()
        self.fifo_path = "/tmp/rfid_pipe"
        self.audio_fifo_path = "/tmp/rfid_audio_pipe"
        self.ready_pipe_path = "/tmp/ready_pipe"
        
        # Define the ready message
        self.ready_message = "READY"
        
        # Base directory for sounds and waveform data
        self.sounds_base_dir = SOUNDS_BASE_DIR
        
        # Cache for waveform data
        self.waveform_cache = {}
        
        # Current active waveform data
        self.current_waveform_data = None
        self.current_tag_id = None
        
        # Build the initial waveform cache
        self.build_waveform_cache()

        # Create the pipes if they don't exist
        if not os.path.exists(self.fifo_path):
            os.mkfifo(self.fifo_path)
            os.chmod(self.fifo_path, 0o666)
            
        if not os.path.exists(self.audio_fifo_path):
            os.mkfifo(self.audio_fifo_path)
            os.chmod(self.audio_fifo_path, 0o666)
            
        if not os.path.exists(self.ready_pipe_path):
            os.mkfifo(self.ready_pipe_path)
            os.chmod(self.ready_pipe_path, 0o666)
            
        print("Waiting for RFID tags...")
        
        # Flag to indicate whether a tag has been scanned
        self.tag_scanned = False
        
        # Flag to indicate whether audio is currently playing
        self.audio_playing = False
        
        # Flag to indicate when a new tag is scanned
        self.new_tag_scanned = False

        # Flag to indicate audio finished naturally
        self.audio_just_finished = False

    def build_waveform_cache(self):
        """Build a cache of all available waveform.json files."""
        print("Building waveform cache...")
        try:
            for item in os.listdir(self.sounds_base_dir):
                if os.path.isdir(os.path.join(self.sounds_base_dir, item)) and item.isdigit():
                    waveform_path = os.path.join(self.sounds_base_dir, item, "waveform.json")
                    if os.path.exists(waveform_path):
                        try:
                            with open(waveform_path, 'r') as f:
                                waveform_data = json.load(f)
                                self.waveform_cache[item] = waveform_data
                                print(f"Cached waveform for tag {item}: {waveform_path}")
                                # Print a preview of the data structure
                                print(f"Data preview for tag {item}:")
                                if isinstance(waveform_data, dict):
                                    for key in waveform_data:
                                        print(f"  - {key}: {type(waveform_data[key])} with {len(str(waveform_data[key]))} chars")
                                elif isinstance(waveform_data, list):
                                    print(f"  - List with {len(waveform_data)} elements")
                                    if waveform_data:
                                        print(f"  - First element type: {type(waveform_data[0])}")
                                else:
                                    print(f"  - Unexpected data type: {type(waveform_data)}")
                        except Exception as e:
                            print(f"Error loading waveform data for tag {item}: {e}")
        except Exception as e:
            print(f"Error building waveform cache: {e}")
        
        print(f"Waveform cache built with {len(self.waveform_cache)} entries")

    def rfid_reader(self):
        print(f"Reading tags from pipe: {self.fifo_path}")
        
        while True:
            try:
                # Open the pipe for reading (blocking operation)
                with open(self.fifo_path, 'r') as fifo:
                    # Read from the pipe (blocks until data is available)
                    tag_id = fifo.readline().strip()
                    if tag_id:
                        print(f"DEBUG: Read tag: '{tag_id}'")
                        
                        with self.lock:
                            # Set the tag_scanned flag to true once any tag is read
                            self.tag_scanned = True
                            
                            # Set audio_playing to true when a new tag is scanned
                            self.audio_playing = True
                            
                            # Set new_tag_scanned flag to true
                            self.new_tag_scanned = True

                            # Reset audio_just_finished flag for new tag
                            self.audio_just_finished = False
                            
                            # Reset wave points to ensure animation starts fresh
                            print(f"DEBUG: New tag scanned, resetting animation")
                            
                            # Prepare the waveform data for the visualizer
                            if tag_id in self.waveform_cache:
                                self.current_waveform_data = self.waveform_cache[tag_id]
                                self.current_tag_id = tag_id
                                print(f"Prepared waveform data for tag {tag_id}")
                            else:
                                self.current_waveform_data = None
                                self.current_tag_id = None
                                print(f"No waveform data available for tag {tag_id}")
                        
                        # Forward the tag ID to the audio player
                        try:
                            with open(self.audio_fifo_path, 'w') as audio_fifo:
                                audio_fifo.write(f"{tag_id}\n")
                                audio_fifo.flush()
                                print(f"Forwarded tag to audio player: {tag_id}")
                        except Exception as e:
                            print(f"Error forwarding tag to audio player: {e}")
            except Exception as e:
                print(f"Error reading from pipe: {e}")
                time.sleep(1)  # Wait before trying to reopen the pipe

    def ready_reader(self):
        """Thread function to read from the ready pipe."""
        print(f"Reading ready signals from pipe: {self.ready_pipe_path}")
        last_ready_time = 0
        ready_cooldown = 5  # Seconds to wait before allowing another reload
        
        while True:
            try:
                # Open the pipe for reading (blocking operation)
                with open(self.ready_pipe_path, 'r') as pipe:
                    # Read from the pipe (blocks until data is available)
                    message = pipe.readline().strip()
                    if message == self.ready_message:
                        print("Received READY signal from audio player")
                        current_time = time.time()
                            
                        with self.lock:
                            # Set audio_playing to false when audio is done
                            was_playing = self.audio_playing
                            self.audio_playing = False
                            self.audio_just_finished = True # Mark that audio finished naturally
                            # DO NOT Clear the new_tag_scanned flag here
                            # Let the animation loop handle it to ensure proper start
                            # self.new_tag_scanned = False 
                            print(f"DEBUG: Audio finished playing, animation should stop. Was playing: {was_playing}")
                            
                            # Force reset wave points to ensure immediate transition
                            print("DEBUG: Forcing immediate transition to flat line")
            except Exception as e:
                print(f"Error reading from ready pipe: {e}")
                time.sleep(1)  # Wait before trying to reopen the pipe

    def run(self):
        # Start the RFID reader in a separate thread
        reader_thread = threading.Thread(target=self.rfid_reader, daemon=True)
        reader_thread.start()
        
        # Start the ready reader in a separate thread
        ready_thread = threading.Thread(target=self.ready_reader, daemon=True)
        ready_thread.start()

        offscreen_canvas = self.matrix.CreateFrameCanvas()
        height = self.matrix.height
        width = self.matrix.width
        
        # Variables for the waveform
        time_var = 0
        wave_height = height // 3  # Maximum wave amplitude
        wave_points = []
        
        # Initialize wave points
        for i in range(width):
            wave_points.append(height // 2)
        
        # Fixed brightness value
        BRIGHTNESS = 200  # Value between 0-255, where 255 is maximum brightness
        
        # Track if we're actually updating sounds
        updating_sounds = False
        last_progress_update_time = time.time()  # Initialize to current time
        progress_timeout = 10  # Seconds to wait before assuming no sounds are being updated
        startup_time = time.time()  # Track when we started
        
        # Track the last time we checked the audio_playing flag
        last_audio_check_time = time.time()
        audio_check_interval = 1.0  # Check every second
        
        while True:
            # Clear the canvas completely
            offscreen_canvas.Clear()
            self.usleep(50 * 1000)  # Slightly slower update for smoother animation
            time_var += 0.2
            
            # Periodically check if audio_playing is false but should be true
            current_time = time.time()
            if current_time - last_audio_check_time > audio_check_interval:
                last_audio_check_time = current_time
                with self.lock:
                    # Failsafe: If a NEW tag was just scanned but audio_playing is still false,
                    # force it to true. This shouldn't normally be needed.
                    if self.new_tag_scanned and not self.audio_playing:
                        print("DEBUG (Periodic Check - Failsafe): New tag scanned but audio_playing is false. Resetting audio_playing=True")
                        self.audio_playing = True
            
            # Get the current state (thread-safe)
            with self.lock:
                has_tag_been_scanned = self.tag_scanned
                audio_playing = self.audio_playing
                new_tag_scanned = self.new_tag_scanned
                
                # Read the audio_just_finished flag (don't reset it here)
                audio_finished_this_cycle = self.audio_just_finished
                # Reset the flag immediately after reading
                # if self.audio_just_finished:
                #    self.audio_just_finished = False
                
                # Reset the new_tag_scanned flag if it was set
                if new_tag_scanned:
                    self.new_tag_scanned = False
                    print(f"DEBUG: Animation loop detected new_tag_scanned is true")
                    
                    # Ensure audio_playing is true when a new tag is scanned
                    if not audio_playing:
                        print(f"DEBUG: Setting audio_playing to true for new tag")
                        self.audio_playing = True
                        audio_playing = True
            
            # Reset wave points if a new tag was scanned
            if new_tag_scanned:
                for x in range(width):
                    wave_points[x] = height // 2
                print("DEBUG: Reset wave points for new tag")
            
            # Only draw waveform when audio is playing
            if has_tag_been_scanned and audio_playing:
                # Use the current waveform data if available
                if self.current_waveform_data is not None:
                    # Use the new method to draw waveform from data
                    self.draw_waveform_from_data(offscreen_canvas, width, height, time_var)
                else:
                    # Fallback to default waveform if no data is available
                    for x in range(width):
                        # Create a smoother waveform using multiple sine waves
                        y = height // 2
                        y += int(wave_height * math.sin(x/7 + time_var) * 0.5)
                        y += int(wave_height * math.sin(x/4 - time_var*0.7) * 0.3)
                        y += int(wave_height * math.sin(x/10 + time_var*0.5) * 0.2)
                        
                        # Add subtle randomness for more natural soundwave look
                        y += random.randint(-2, 2)
                        
                        # Keep within bounds
                        y = max(1, min(height-2, y))
                        wave_points[x] = y
                    
                    # Draw the waveform
                    for x in range(width):
                        # Draw vertical lines for each point of the waveform
                        mid_point = height // 2
                        amplitude = wave_points[x] - mid_point
                        
                        # Mirror the wave to get the classic soundwave effect
                        start_y = mid_point - abs(amplitude)
                        end_y = mid_point + abs(amplitude)
                        
                        for y in range(start_y, end_y + 1):
                            offscreen_canvas.SetPixel(x, y, 255, 0, 0)
            else:
                # Immediately reset wave points to a flat line when audio stops
                for x in range(width):
                    wave_points[x] = height // 2
                
                # Before any tag is scanned or when audio is not playing,
                # just draw a single horizontal line
                mid_point = height // 2
                for x in range(width):
                    offscreen_canvas.SetPixel(x, mid_point, 255, 0, 0)
            
            # Update the canvas
            offscreen_canvas = self.matrix.SwapOnVSync(offscreen_canvas)

    def draw_waveform_from_data(self, canvas, width, height, time_var):
        """Draw a waveform based on the cached waveform.json data."""
        if self.current_waveform_data is None:
            return
            
        # Get the waveform data
        waveform_data = self.current_waveform_data
        
        # Default values
        mid_point = height // 2
        max_amplitude = height // 3  # Maximum wave amplitude
        
        # Extract frequency bands from waveform data if available
        bands = []
        if isinstance(waveform_data, dict):
            # Try to get frequency bands from the data
            if 'bands' in waveform_data and isinstance(waveform_data['bands'], list):
                bands = waveform_data['bands']
            elif 'frequencies' in waveform_data and isinstance(waveform_data['frequencies'], list):
                bands = waveform_data['frequencies']
            elif 'amplitudes' in waveform_data and isinstance(waveform_data['amplitudes'], list):
                bands = waveform_data['amplitudes']
        elif isinstance(waveform_data, list):
            # If the data is a list of lists, use the first array
            if waveform_data and isinstance(waveform_data[0], list):
                bands = waveform_data[0]
            else:
                # If it's a single list, use it directly
                bands = waveform_data
        
        # If we have bands data, use it to create the visualization
        if bands:
            # Calculate width of each band to fill screen
            band_width = width / len(bands)
            
            # Draw each band
            for i, amplitude in enumerate(bands):
                # Calculate x position for this band
                x = int(i * band_width)
                
                # Scale the amplitude to fit the screen height
                # Assuming input values are in the range of 0-15 based on the data we saw
                scaled_amplitude = int((amplitude / 15.0) * max_amplitude)
                
                # Draw a vertical line for this band
                start_y = mid_point - scaled_amplitude
                end_y = mid_point + scaled_amplitude
                
                # Ensure we stay within bounds
                start_y = max(0, min(height - 1, start_y))
                end_y = max(0, min(height - 1, end_y))
                
                # Draw the line
                for y in range(start_y, end_y + 1):
                    canvas.SetPixel(x, y, 255, 0, 0)  # Red color for the waveform
        else:
            # Fallback to a more dynamic waveform if no bands data
            # Try to extract any useful data from the waveform
            wave_height = max_amplitude
            
            if isinstance(waveform_data, dict):
                # Use any amplitude data if available
                if 'amplitude' in waveform_data:
                    wave_height = min(max_amplitude, waveform_data['amplitude'])
                
                # Use any frequency data if available
                frequency = 1.0
                if 'frequency' in waveform_data:
                    frequency = max(0.1, min(5.0, waveform_data['frequency']))
                
                # Generate wave points
                for x in range(width):
                    y = mid_point
                    
                    # Create a smoother waveform using multiple sine waves
                    y += int(wave_height * math.sin(x/7 + time_var) * 0.5)
                    y += int(wave_height * math.sin(x/4 - time_var*0.7) * 0.3)
                    y += int(wave_height * math.sin(x/10 + time_var*0.5) * 0.2)
                    
                    # Add subtle randomness for more natural soundwave look
                    y += random.randint(-2, 2)
                    
                    # Keep within bounds
                    y = max(1, min(height-2, y))
                    
                    # Draw vertical line for this point
                    amplitude = y - mid_point
                    start_y = mid_point - abs(amplitude)
                    end_y = mid_point + abs(amplitude)
                    
                    for y_pos in range(start_y, end_y + 1):
                        canvas.SetPixel(x, y_pos, 255, 0, 0)
            else:
                # If waveform_data is not a dict, fall back to default visualization
                for x in range(width):
                    y = mid_point
                    y += int(wave_height * math.sin(x/7 + time_var) * 0.5)
                    y += int(wave_height * math.sin(x/4 - time_var*0.7) * 0.3)
                    y += int(wave_height * math.sin(x/10 + time_var*0.5) * 0.2)
                    
                    # Add subtle randomness for more natural soundwave look
                    y += random.randint(-2, 2)
                    
                    # Keep within bounds
                    y = max(1, min(height-2, y))
                    
                    # Draw vertical line for this point
                    amplitude = y - mid_point
                    start_y = mid_point - abs(amplitude)
                    end_y = mid_point + abs(amplitude)
                    
                    for y_pos in range(start_y, end_y + 1):
                        canvas.SetPixel(x, y_pos, 255, 0, 0)

# Main function
if __name__ == "__main__":
    waveform = WaveformAnimation()
    if (not waveform.process()):
        waveform.print_help()
