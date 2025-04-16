#!/usr/bin/env python3
from samplebase import SampleBase
import math
import random
import threading
import time
import os
import json

class WaveformAnimation(SampleBase):
    def __init__(self, *args, **kwargs):
        super(WaveformAnimation, self).__init__(*args, **kwargs)
        self.lock = threading.Lock()
        self.fifo_path = "/tmp/rfid_pipe"
        self.audio_fifo_path = "/tmp/rfid_audio_pipe"
        self.ready_pipe_path = "/tmp/ready_pipe"
        self.ready_message = "READY"
        self.show_ready_message = False
        self.ready_message_time = 0
        self.ready_message_duration = 5  # Show ready message for 5 seconds
        
        # Use the same path as the audio player
        self.sounds_dir = "/home/fcc-005/sound-machine-firmware/sounds"
        print(f"DEBUG: Sounds directory set to: {self.sounds_dir}")
        
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
            
        # Single color for all tags (red)
        self.current_color = [255, 0, 0]
            
        print("Starting with red color. Waiting for RFID tags...")
        
        # Flag to indicate whether a tag has been scanned
        self.tag_scanned = False
        
        # Flag to indicate whether audio is currently playing
        self.audio_playing = False
        
        # Flag to indicate when a new tag is scanned
        self.new_tag_scanned = False

        # Flag to indicate audio finished naturally
        self.audio_just_finished = False

    def load_all_tag_colors(self):
        """No longer needed since we use a single color."""
        pass

    def reload_tag_colors(self):
        """No longer needed since we use a single color."""
        pass

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
                            
                            # Always use red color
                            self.current_color = [255, 0, 0]
                            print(f"DEBUG: Set color to red")
                            print(f"DEBUG: New tag scanned, set audio_playing to true")
                            
                            # Reset wave points to ensure animation starts fresh
                            print(f"DEBUG: New tag scanned, resetting animation")
                        
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
                        
                        # Only reload colors if enough time has passed since the last reload
                        if current_time - last_ready_time > ready_cooldown:
                            print("System ready, reloading tag colors...")
                            self.reload_tag_colors()
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
        
        # Fixed brightness value for all colors
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
            
            # Get current color values (no transitions)
            red = self.current_color[0]
            green = self.current_color[1]
            blue = self.current_color[2]
            
            # Reset wave points if a new tag was scanned
            if new_tag_scanned:
                for x in range(width):
                    wave_points[x] = height // 2
                print("DEBUG: Reset wave points for new tag")
            
            # Only draw waveform when audio is playing
            if has_tag_been_scanned and audio_playing:
                print(f"DEBUG: Drawing waveform, audio_playing={audio_playing}, has_tag_been_scanned={has_tag_been_scanned}")
                # Generate new wave points based on sine waves and some randomness
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
                        # Set the pixel with the current color
                        offscreen_canvas.SetPixel(x, y, red, green, blue)
            else:
                # Immediately reset wave points to a flat line when audio stops
                for x in range(width):
                    wave_points[x] = height // 2
                
                # Before any tag is scanned or when audio is not playing,
                # just draw a single horizontal line in red (255, 0, 0)
                mid_point = height // 2
                for x in range(width):
                    offscreen_canvas.SetPixel(x, mid_point, 255, 0, 0)
                
                # Debug print when not drawing waveform
                if has_tag_been_scanned and not audio_playing:
                    print(f"DEBUG: Not drawing waveform, audio_playing={audio_playing}, has_tag_been_scanned={has_tag_been_scanned}")
            
            # Update the canvas
            offscreen_canvas = self.matrix.SwapOnVSync(offscreen_canvas)

# Main function
if __name__ == "__main__":
    waveform = WaveformAnimation()
    if (not waveform.process()):
        waveform.print_help()
