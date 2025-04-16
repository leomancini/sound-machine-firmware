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
                            
                            # Always use red color
                            self.current_color = [255, 0, 0]
                            print(f"DEBUG: Set color to red")
                        
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
                            self.audio_playing = False
                            print("DEBUG: Audio finished playing, animation should stop")
                            
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
        
        while True:
            # Clear the canvas completely
            offscreen_canvas.Clear()
            self.usleep(50 * 1000)  # Slightly slower update for smoother animation
            time_var += 0.2
            
            # Get the current state (thread-safe)
            with self.lock:
                has_tag_been_scanned = self.tag_scanned
                audio_playing = self.audio_playing
                
                # Debug print to track audio_playing state
                if not audio_playing and has_tag_been_scanned:
                    print("DEBUG: Animation loop detected audio_playing is false")
            
            # Get current color values (no transitions)
            red = self.current_color[0]
            green = self.current_color[1]
            blue = self.current_color[2]
            
            # Only draw waveform when audio is playing
            if has_tag_been_scanned and audio_playing:
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
            
            # Update the canvas
            offscreen_canvas = self.matrix.SwapOnVSync(offscreen_canvas)

# Main function
if __name__ == "__main__":
    waveform = WaveformAnimation()
    if (not waveform.process()):
        waveform.print_help()
