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
        
        # Frame counter for animation
        self.frame_counter = 0
        
        # Audio sync variables
        self.audio_start_time = 0
        self.audio_duration = 0  # Duration in seconds
        self.frames_per_second = 30  # Increased from 15 to 30 for better sync
        
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
        
        # Audio sync tracking
        self.last_audio_position = 0
        self.audio_position = 0
        self.audio_frame_count = 0

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
                            
                            # Reset audio sync tracking
                            self.frame_counter = 0
                            self.audio_position = 0
                            self.audio_frame_count = 0
                            
                            # Prepare the waveform data for the visualizer
                            if tag_id in self.waveform_cache:
                                self.current_waveform_data = self.waveform_cache[tag_id]
                                self.current_tag_id = tag_id
                                print(f"Prepared waveform data for tag {tag_id}")
                                
                                # Verify that the waveform data is valid
                                if self.current_waveform_data is None or (isinstance(self.current_waveform_data, list) and len(self.current_waveform_data) == 0):
                                    print(f"WARNING: Waveform data for tag {tag_id} is empty or invalid")
                                    # Don't set current_waveform_data to None here, keep the previous value
                            else:
                                print(f"No waveform data available for tag {tag_id}")
                                # Don't reset current_waveform_data here, keep the previous value
                        
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
                        
                        # Add a cooldown to prevent rapid transitions
                        if current_time - last_ready_time < ready_cooldown:
                            print(f"DEBUG: Ignoring READY signal due to cooldown")
                            continue
                            
                        last_ready_time = current_time
                            
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
        BRIGHTNESS = 255  # Value between 0-255, where 255 is maximum brightness
        
        # Track if we're actually updating sounds
        updating_sounds = False
        last_progress_update_time = time.time()  # Initialize to current time
        progress_timeout = 10  # Seconds to wait before assuming no sounds are being updated
        startup_time = time.time()  # Track when we started
        
        # Track the last time we checked the audio_playing flag
        last_audio_check_time = time.time()
        audio_check_interval = 1.0  # Check every second
        
        # Add a minimum animation duration to ensure the waveform is visible
        min_animation_duration = 2.0  # seconds
        animation_start_time = 0
        animation_running = False
        
        # Track the last tag ID to detect new tags
        last_tag_id = None
        
        # Track when the audio finished playing
        audio_finished_time = 0
        audio_finished = False
        
        # Track if we've already extended the animation after audio finished
        extended_after_audio_finished = False
        
        while True:
            # Clear the canvas completely
            offscreen_canvas.Clear()
            self.usleep(50 * 1000)  # Slightly slower update for smoother animation
            
            # Get the current state (thread-safe)
            with self.lock:
                has_tag_been_scanned = self.tag_scanned
                audio_playing = self.audio_playing
                new_tag_scanned = self.new_tag_scanned
                current_tag_id = self.current_tag_id
                
                # Read the audio_just_finished flag (don't reset it here)
                audio_finished_this_cycle = self.audio_just_finished
                
                # If audio just finished, record the time
                if audio_finished_this_cycle:
                    audio_finished_time = time.time()
                    audio_finished = True
                    extended_after_audio_finished = False
                    print(f"DEBUG: Audio finished at {audio_finished_time}")
                
                # Reset the new_tag_scanned flag if it was set
                if new_tag_scanned:
                    self.new_tag_scanned = False
                    print(f"DEBUG: Animation loop detected new_tag_scanned is true")
                    
                    # Reset frame counter when a new tag is scanned
                    self.frame_counter = 0
                    
                    # Start the minimum animation duration timer
                    animation_start_time = time.time()
                    animation_running = True
                    
                    # Reset audio finished state for new tag
                    audio_finished = False
                    extended_after_audio_finished = False
                    
                    # Ensure audio_playing is true when a new tag is scanned
                    if not audio_playing:
                        print(f"DEBUG: Setting audio_playing to true for new tag")
                        self.audio_playing = True
                        audio_playing = True
                
                # Check if we have a new tag ID
                if current_tag_id != last_tag_id and current_tag_id is not None:
                    print(f"DEBUG: New tag ID detected: {current_tag_id}")
                    last_tag_id = current_tag_id
                    
                    # Start the minimum animation duration timer
                    animation_start_time = time.time()
                    animation_running = True
                    
                    # Reset audio finished state for new tag
                    audio_finished = False
                    extended_after_audio_finished = False
                    
                    # Ensure audio_playing is true for the new tag
                    if not audio_playing:
                        print(f"DEBUG: Setting audio_playing to true for new tag ID")
                        self.audio_playing = True
                        audio_playing = True
            
            # Check if we should continue animation based on minimum duration
            current_time = time.time()
            
            # Determine if we should continue the animation
            should_continue_animation = False
            
            # Continue if we're in the minimum animation duration period
            if animation_running and (current_time - animation_start_time < min_animation_duration):
                should_continue_animation = True
                print(f"DEBUG: Forcing animation to continue for minimum duration")
            # Continue if audio is still playing
            elif audio_playing:
                should_continue_animation = True
                print(f"DEBUG: Continuing animation because audio is still playing")
            # Continue if audio just finished and we haven't reached the minimum duration
            elif audio_finished and not extended_after_audio_finished and (current_time - audio_finished_time < min_animation_duration):
                should_continue_animation = True
                print(f"DEBUG: Continuing animation after audio finished for minimum duration")
            else:
                # Animation has run for the minimum duration and audio is not playing
                animation_running = False
                
                # If audio finished and we've extended the animation, mark it as done
                if audio_finished and not extended_after_audio_finished and (current_time - audio_finished_time >= min_animation_duration):
                    extended_after_audio_finished = True
                    print(f"DEBUG: Stopping animation after minimum duration since audio finished")
                
                # If we've extended the animation after audio finished, we can reset the audio_finished flag
                if extended_after_audio_finished:
                    audio_finished = False
            
            # Set audio_playing based on our decision
            if should_continue_animation:
                audio_playing = True
            else:
                audio_playing = False
            
            # Only increment frame counter when audio is playing
            if audio_playing:
                self.frame_counter += 1
                time_var = self.frame_counter
            
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
            print("DEBUG: No waveform data available, falling back to default visualization")
            return
            
        # Get the waveform data
        waveform_data = self.current_waveform_data
        
        # Default values
        mid_point = height // 2
        max_amplitude = height // 3  # Reduced from height // 2 to make waveform less heavy
        
        # Extract frequency bands from waveform data if available
        bands = []

        # Use time_var to cycle through frames at a slower rate
        # Adjust the frame rate to match audio playback
        # Calculate the frame index based on the current time and audio position
        if isinstance(waveform_data, list) and waveform_data:
            # Calculate how many frames we have in total
            total_frames = len(waveform_data)
            
            if total_frames == 0:
                print("DEBUG: Waveform data is an empty list, falling back to default visualization")
                return
                
            # Calculate the current frame based on time_var and audio position
            # This helps synchronize the visualization with the audio
            frame_index = int((time_var / self.frames_per_second) * total_frames) % total_frames
            
            # Get the bands for the current frame
            bands = waveform_data[frame_index]
            
            # Update audio position tracking
            self.audio_position = frame_index / total_frames
            self.audio_frame_count = frame_index
        
        # If we have bands data, use it to create the visualization
        if bands:
            # Find the maximum amplitude for better scaling
            max_band_value = max(bands) if bands else 15.0
            
            # Calculate width of each band to fill screen
            band_width = width / len(bands)
            
            # Find the dominant frequency (highest amplitude)
            dominant_amplitude = max(bands) if bands else 0
            dominant_indices = [i for i, amp in enumerate(bands) if amp == dominant_amplitude]
            
            # Draw each band
            for i, amplitude in enumerate(bands):
                # Normalize amplitude to 0-1 range
                normalized_amplitude = amplitude / max_band_value
                
                # Apply a power function to emphasize higher values
                # Lower power value (0.4) will make spikes even more prominent
                emphasized_amplitude = normalized_amplitude ** 0.4
                
                # Add a minimum threshold to ensure small values are still visible
                if emphasized_amplitude < 0.05 and emphasized_amplitude > 0:
                    emphasized_amplitude = 0.05
                
                # Scale to appropriate display height
                scaled_amplitude = int(emphasized_amplitude * max_amplitude)
                
                # Calculate x position for this band
                x = int(i * band_width)
                
                # Calculate width of the band (ensure minimum of 1 pixel)
                # Reduce the width to make the waveform thinner
                band_pixel_width = max(1, int(band_width * 0.7))  # Reduced to 70% of original width
                
                # Center the band within its allocated space
                x_offset = int((band_width - band_pixel_width) / 2)
                x += x_offset
                
                # Mirror the wave to get the classic soundwave effect
                start_y = mid_point - scaled_amplitude
                end_y = mid_point + scaled_amplitude
                
                # Keep within bounds
                start_y = max(0, min(height - 1, start_y))
                end_y = max(0, min(height - 1, end_y))
                
                # Draw filled rectangle for this frequency band
                for y in range(start_y, end_y + 1):
                    # Use only red at full brightness (255, 0, 0)
                    red = 255
                    green = 0
                    blue = 0
                    
                    # Draw a horizontal line for this y-coordinate
                    for x_pos in range(x, min(x + band_pixel_width, width)):
                        canvas.SetPixel(x_pos, y, red, green, blue)
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
                    
                    # Draw a thinner line (1 pixel wide)
                    for y_pos in range(start_y, end_y + 1):
                        # Use only red at full brightness (255, 0, 0)
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
                    
                    # Draw a thinner line (1 pixel wide)
                    for y_pos in range(start_y, end_y + 1):
                        # Use only red at full brightness (255, 0, 0)
                        canvas.SetPixel(x, y_pos, 255, 0, 0)

# Main function
if __name__ == "__main__":
    waveform = WaveformAnimation()
    if (not waveform.process()):
        waveform.print_help()
