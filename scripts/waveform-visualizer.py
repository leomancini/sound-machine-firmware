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
        self.progress_pipe_path = "/tmp/progress_pipe"
        self.ready_message = "READY"
        self.show_ready_message = False
        self.ready_message_time = 0
        self.ready_message_duration = 5  # Show ready message for 5 seconds
        self.show_loading_message = True  # Start with loading message
        self.loading_progress = 0  # Progress percentage (0-100)
        self.loading_message = "Loading sounds..."  # Current loading message
        self.initial_loading = True  # Flag to indicate initial loading phase
        self.initial_loading_timeout = 30  # Seconds to show initial loading screen
        
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
            
        if not os.path.exists(self.progress_pipe_path):
            os.mkfifo(self.progress_pipe_path)
            os.chmod(self.progress_pipe_path, 0o666)
            
        # Single color for all tags (red)
        self.current_color = [255, 0, 0]
            
        print("Starting with red color. Waiting for RFID tags...")
        
        # Flag to indicate whether a tag has been scanned
        self.tag_scanned = False

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
                            self.show_loading_message = False  # Hide loading message
                            self.show_ready_message = True
                            self.ready_message_time = time.time()
            except Exception as e:
                print(f"Error reading from ready pipe: {e}")
                time.sleep(1)  # Wait before trying to reopen the pipe

    def progress_reader(self):
        """Thread function to read progress updates from the progress pipe."""
        print(f"Reading progress updates from pipe: {self.progress_pipe_path}")
        last_sync_complete_time = 0
        sync_complete_cooldown = 5  # Seconds to wait before allowing another reload
        
        while True:
            try:
                # Open the pipe for reading (blocking operation)
                with open(self.progress_pipe_path, 'r') as pipe:
                    # Read from the pipe (blocks until data is available)
                    data = pipe.readline().strip()
                    if data:
                        try:
                            progress, message = data.split(',', 1)
                            progress = int(progress)
                            
                            # Check if the message contains a tag ID
                            tag_id = None
                            if "Updating sound" in message:
                                # Extract the tag ID from the message
                                parts = message.split("Updating sound")
                                if len(parts) > 1:
                                    tag_id = parts[1].strip()
                                    
                                    # Check if the sound directory exists for this tag
                                    sound_dir = os.path.join(self.sounds_dir, tag_id)
                                    if not os.path.exists(sound_dir):
                                        print(f"DEBUG: Skipping progress update for non-existent sound: {tag_id}")
                                        continue
                            
                            # Check if this is a sync completion message
                            current_time = time.time()
                            if "Sound synchronization complete" in message or "System ready" in message:
                                # Only reload colors if enough time has passed since the last reload
                                if current_time - last_sync_complete_time > sync_complete_cooldown:
                                    print("Sync completed, reloading tag colors...")
                                    self.reload_tag_colors()
                                    last_sync_complete_time = current_time
                            
                            with self.lock:
                                self.loading_progress = progress
                                self.loading_message = message
                                # Always show loading message when we receive a progress update
                                self.show_loading_message = True
                                print(f"Progress update: {progress}% - {message}")
                        except ValueError:
                            print(f"Invalid progress data: {data}")
            except Exception as e:
                print(f"Error reading from progress pipe: {e}")
                time.sleep(1)  # Wait before trying to reopen the pipe

    def draw_text(self, canvas, text, x, y, color):
        """Draw text on the canvas."""
        # Simple 5x7 font for displaying text
        font = {
            'R': [
                [1, 1, 1, 1, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 1, 1, 1, 1],
                [1, 0, 1, 0, 0],
                [1, 0, 0, 1, 0],
                [1, 0, 0, 0, 1]
            ],
            'E': [
                [1, 1, 1, 1, 1],
                [1, 0, 0, 0, 0],
                [1, 0, 0, 0, 0],
                [1, 1, 1, 1, 0],
                [1, 0, 0, 0, 0],
                [1, 0, 0, 0, 0],
                [1, 1, 1, 1, 1]
            ],
            'A': [
                [0, 0, 1, 0, 0],
                [0, 1, 0, 1, 0],
                [1, 0, 0, 0, 1],
                [1, 1, 1, 1, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1]
            ],
            'D': [
                [1, 1, 1, 1, 0],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 1, 1, 1, 0]
            ],
            'Y': [
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [0, 1, 0, 1, 0],
                [0, 0, 1, 0, 0],
                [0, 0, 1, 0, 0],
                [0, 0, 1, 0, 0],
                [0, 0, 1, 0, 0]
            ],
            'L': [
                [1, 0, 0, 0, 0],
                [1, 0, 0, 0, 0],
                [1, 0, 0, 0, 0],
                [1, 0, 0, 0, 0],
                [1, 0, 0, 0, 0],
                [1, 0, 0, 0, 0],
                [1, 1, 1, 1, 1]
            ],
            'O': [
                [0, 1, 1, 1, 0],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [0, 1, 1, 1, 0]
            ],
            'I': [
                [0, 0, 1, 0, 0],
                [0, 0, 1, 0, 0],
                [0, 0, 1, 0, 0],
                [0, 0, 1, 0, 0],
                [0, 0, 1, 0, 0],
                [0, 0, 1, 0, 0],
                [0, 0, 1, 0, 0]
            ],
            'N': [
                [1, 0, 0, 0, 1],
                [1, 1, 0, 0, 1],
                [1, 0, 1, 0, 1],
                [1, 0, 0, 1, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1]
            ],
            'G': [
                [0, 1, 1, 1, 0],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 0],
                [1, 0, 1, 1, 1],
                [1, 0, 0, 0, 1],
                [1, 0, 0, 0, 1],
                [0, 1, 1, 1, 0]
            ],
            '.': [
                [0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0],
                [0, 0, 1, 0, 0],
                [0, 0, 1, 0, 0]
            ],
            '%': [
                [1, 0, 0, 0, 1],
                [1, 0, 0, 1, 0],
                [0, 0, 0, 1, 0],
                [0, 0, 1, 0, 0],
                [0, 1, 0, 0, 0],
                [0, 1, 0, 0, 1],
                [1, 0, 0, 0, 1]
            ]
        }
        
        # Draw each character
        char_width = 5
        char_height = 7
        char_spacing = 1
        
        # Calculate total width of the text to center it properly
        total_width = 0
        for char in text:
            if char in font:
                total_width += char_width + char_spacing
        
        # Calculate starting x position to center the text
        start_x = x - total_width // 2
        
        # Draw each character
        for i, char in enumerate(text):
            if char in font:
                # Calculate position for this character
                char_x = start_x + i * (char_width + char_spacing)
                
                for row in range(char_height):
                    for col in range(char_width):
                        if font[char][row][col] == 1:
                            # Draw the pixel - flip both horizontally and vertically
                            # Horizontal flip: (char_width - 1 - col)
                            # Vertical flip: (char_height - 1 - row)
                            canvas.SetPixel(char_x + (char_width - 1 - col), y + (char_height - 1 - row), color[0], color[1], color[2])

    def draw_progress_bar(self, canvas, x, y, width, height, progress, color):
        """Draw a progress bar on the canvas."""
        # Draw the background (empty bar)
        for i in range(x, x + width):
            for j in range(y, y + height):
                canvas.SetPixel(i, j, 50, 50, 50)  # Dark gray background
        
        # Calculate the filled portion width
        filled_width = int(width * progress / 100)
        
        # Draw the filled portion
        for i in range(x, x + filled_width):
            for j in range(y, y + height):
                canvas.SetPixel(i, j, color[0], color[1], color[2])

    def run(self):
        # Start the RFID reader in a separate thread
        reader_thread = threading.Thread(target=self.rfid_reader, daemon=True)
        reader_thread.start()
        
        # Start the ready reader in a separate thread
        ready_thread = threading.Thread(target=self.ready_reader, daemon=True)
        ready_thread.start()
        
        # Start the progress reader in a separate thread
        progress_thread = threading.Thread(target=self.progress_reader, daemon=True)
        progress_thread.start()

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
                show_ready = self.show_ready_message
                ready_time = self.ready_message_time
                show_loading = self.show_loading_message
                loading_progress = self.loading_progress
                loading_message = self.loading_message
            
            # Check if ready message should be hidden
            if show_ready and time.time() - ready_time > self.ready_message_duration:
                with self.lock:
                    self.show_ready_message = False
            
            # Check if we're actually updating sounds
            current_time = time.time()
            
            # During initial loading phase, keep showing the loading screen
            if self.initial_loading:
                if current_time - startup_time > self.initial_loading_timeout:
                    self.initial_loading = False
                    print("Initial loading phase complete")
                else:
                    # Keep showing loading screen during initial phase
                    with self.lock:
                        self.show_loading_message = True
            else:
                # After initial phase, use normal timeout logic
                if "Updating sound" in loading_message:
                    updating_sounds = True
                    last_progress_update_time = current_time
                elif current_time - last_progress_update_time > progress_timeout:
                    updating_sounds = False
                    with self.lock:
                        self.show_loading_message = False
            
            # Get current color values (no transitions)
            red = self.current_color[0]
            green = self.current_color[1]
            blue = self.current_color[2]
            
            # Draw loading message if needed
            if show_loading:
                # Draw the progress bar - full screen (64x32)
                bar_width = width  # Full width
                bar_height = height  # Full height
                bar_x = 0  # Start from left edge
                bar_y = 0  # Start from top edge
                
                # Draw the progress bar with red color
                self.draw_progress_bar(offscreen_canvas, bar_x, bar_y, bar_width, bar_height, 
                                      loading_progress, (255, 0, 0))  # Red color
            else:
                # Only draw waveform when not in loading state and not showing READY message
                if has_tag_been_scanned and not show_ready:
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
                    # Before any tag is scanned or when showing READY, just draw a single horizontal gray line
                    mid_point = height // 2
                    for x in range(width):
                        offscreen_canvas.SetPixel(x, mid_point, BRIGHTNESS, BRIGHTNESS, BRIGHTNESS)
            
            # Draw ready message if needed
            if show_ready:
                # Calculate position to center the text
                text = "READY"
                text_width = len(text) * 6  # 5 pixels wide + 1 pixel spacing
                text_x = width // 2  # Center horizontally
                text_y = 14  # Fixed position for 64x32 matrix
                
                # Draw the text in white
                self.draw_text(offscreen_canvas, text, text_x, text_y, (255, 255, 255))
            
            # Update the canvas
            offscreen_canvas = self.matrix.SwapOnVSync(offscreen_canvas)

# Main function
if __name__ == "__main__":
    waveform = WaveformAnimation()
    if (not waveform.process()):
        waveform.print_help()
