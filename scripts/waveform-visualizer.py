#!/usr/bin/env python3
from samplebase import SampleBase
import math
import random
import threading
import time
import os

class WaveformAnimation(SampleBase):
    def __init__(self, *args, **kwargs):
        super(WaveformAnimation, self).__init__(*args, **kwargs)
        self.color_scheme = -1  # Start with grey (-1 = grey, 1 = red, 3 = blue)
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
            
        # Flag to indicate whether a tag has been scanned
        self.tag_scanned = False
            
        print("Starting in grey mode. Waiting for RFID tags...")
        print("  - 0008479619 will turn display RED")
        print("  - 0026068654 will turn display BLUE")
        print("Any other input will return to GREY")

    def rfid_reader(self):
        print(f"Reading tags from pipe: {self.fifo_path}")
        while True:
            try:
                # Open the pipe for reading (blocking operation)
                with open(self.fifo_path, 'r') as fifo:
                    # Read from the pipe (blocks until data is available)
                    tag_id = fifo.readline().strip()
                    if tag_id:
                        print(f"Read tag: '{tag_id}'")
                        
                        with self.lock:
                            # Set the tag_scanned flag to true once any tag is read
                            self.tag_scanned = True
                            
                            if tag_id == "0008479619":
                                print("Recognized RED tag")
                                self.color_scheme = 1  # Red
                            elif tag_id == "0026068654":
                                print("Recognized BLUE tag")
                                self.color_scheme = 3  # Blue
                            else:
                                print(f"Unknown tag: '{tag_id}', setting to GREY")
                                self.color_scheme = -1  # Grey
                        
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
        while True:
            try:
                # Open the pipe for reading (blocking operation)
                with open(self.ready_pipe_path, 'r') as pipe:
                    # Read from the pipe (blocks until data is available)
                    message = pipe.readline().strip()
                    if message == self.ready_message:
                        print("Received READY signal from audio player")
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
                            with self.lock:
                                self.loading_progress = progress
                                self.loading_message = message
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
        
        # Adjust starting x position to account for horizontal flip
        x = x + total_width - char_spacing
        
        # Pre-calculate all pixels to draw for better performance
        pixels_to_draw = []
        
        for i, char in enumerate(text):
            if char in font:
                # Calculate position with horizontal flip
                char_x = x - i * (char_width + char_spacing)
                
                for row in range(char_height):
                    for col in range(char_width):
                        if font[char][row][col] == 1:
                            # Flip vertically by calculating the flipped y position
                            flipped_y = y + (char_height - 1 - row)
                            pixels_to_draw.append((char_x + col, flipped_y, color[0], color[1], color[2]))
        
        # Draw all pixels at once
        for px, py, r, g, b in pixels_to_draw:
            canvas.SetPixel(px, py, r, g, b)

    def draw_progress_bar(self, canvas, x, y, width, height, progress, color):
        """Draw a progress bar on the canvas."""
        # Pre-calculate all pixels to draw for better performance
        pixels_to_draw = []
        
        # Draw the background (empty bar)
        for i in range(x, x + width):
            for j in range(y, y + height):
                pixels_to_draw.append((i, j, 50, 50, 50))  # Dark gray background
        
        # Calculate the filled portion width
        filled_width = int(width * progress / 100)
        
        # Draw the filled portion
        for i in range(x, x + filled_width):
            for j in range(y, y + height):
                pixels_to_draw.append((i, j, color[0], color[1], color[2]))
        
        # Draw all pixels at once
        for px, py, r, g, b in pixels_to_draw:
            canvas.SetPixel(px, py, r, g, b)

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
        
        last_scheme = None
        last_progress = -1  # Track last progress value to avoid unnecessary redraws
        
        # Fixed brightness value for all colors
        BRIGHTNESS = 180  # Value between 0-255, where 255 is maximum brightness
        
        # Cache for color values
        color_cache = {}
        
        while True:
            offscreen_canvas.Clear()
            self.usleep(100 * 1000)  # Slower update for better performance (100ms instead of 50ms)
            time_var += 0.2
            
            # Get the current color scheme (thread-safe)
            with self.lock:
                current_scheme = self.color_scheme
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
            
            # Print debug message when color scheme changes
            if last_scheme != current_scheme:
                if current_scheme == -1:
                    print("NOW DISPLAYING: GREY")
                elif current_scheme == 1:
                    print("NOW DISPLAYING: RED")
                elif current_scheme == 3:
                    print("NOW DISPLAYING: BLUE")
                else:
                    print(f"NOW DISPLAYING: SCHEME {current_scheme}")
                last_scheme = current_scheme
            
            # Set colors based on the color scheme, with fixed brightness
            if current_scheme == -1:  # Grey (default)
                # Equal RGB values for grey
                red = BRIGHTNESS
                green = BRIGHTNESS
                blue = BRIGHTNESS
            elif current_scheme == 1:  # Red dominant (specific for 0008479619)
                red = BRIGHTNESS
                green = 0
                blue = 0
            elif current_scheme == 3:  # Blue dominant (specific for 0026068654)
                red = 0
                green = 0
                blue = BRIGHTNESS
            else:  # Fallback to grey
                red = BRIGHTNESS
                green = BRIGHTNESS
                blue = BRIGHTNESS
            
            # Check if a tag has been scanned
            if has_tag_been_scanned:
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
                        # Gradient color based on distance from center
                        intensity = 1.0 - (abs(y - mid_point) / float(height//2))
                        
                        # Apply intensity to maintain wave shape but keep overall brightness consistent
                        pixel_red = int(red * intensity)
                        pixel_green = int(green * intensity)
                        pixel_blue = int(blue * intensity)
                        
                        offscreen_canvas.SetPixel(x, y, pixel_red, pixel_green, pixel_blue)
            else:
                # Before any tag is scanned, just draw a single horizontal gray line
                mid_point = height // 2
                for x in range(width):
                    offscreen_canvas.SetPixel(x, mid_point, BRIGHTNESS, BRIGHTNESS, BRIGHTNESS)
            
            # Draw loading message if needed
            if show_loading:
                # Only redraw if progress has changed
                if loading_progress != last_progress:
                    # Draw the loading message
                    text = "LOADING"
                    text_width = len(text) * 6  # 5 pixels wide + 1 pixel spacing
                    text_x = (width - text_width) // 2
                    text_y = (height - 7) // 2 - 10  # Position above the progress bar
                    
                    # Draw the text in white
                    self.draw_text(offscreen_canvas, text, text_x, text_y, (255, 255, 255))
                    
                    # Draw the progress bar
                    bar_width = width - 20  # Leave some margin
                    bar_height = 5
                    bar_x = 10
                    bar_y = (height - 7) // 2 + 5  # Position below the text
                    
                    # Draw the progress bar
                    self.draw_progress_bar(offscreen_canvas, bar_x, bar_y, bar_width, bar_height, 
                                          loading_progress, (255, 255, 255))
                    
                    # Draw the progress percentage
                    percent_text = f"{loading_progress}%"
                    percent_width = len(percent_text) * 6
                    percent_x = (width - percent_width) // 2
                    percent_y = bar_y + bar_height + 5
                    
                    # Draw the percentage text
                    self.draw_text(offscreen_canvas, percent_text, percent_x, percent_y, (255, 255, 255))
                    
                    # Draw the loading message
                    message_text = loading_message
                    message_width = len(message_text) * 6
                    message_x = (width - message_width) // 2
                    message_y = percent_y + 10
                    
                    # Draw the message text
                    self.draw_text(offscreen_canvas, message_text, message_x, message_y, (255, 255, 255))
                    
                    last_progress = loading_progress
            
            # Draw ready message if needed
            if show_ready:
                # Calculate position to center the text
                text = "READY"
                text_width = len(text) * 6  # 5 pixels wide + 1 pixel spacing
                text_x = (width - text_width) // 2
                text_y = (height - 7) // 2  # 7 pixels high
                
                # Draw the text in white
                self.draw_text(offscreen_canvas, text, text_x, text_y, (255, 255, 255))
            
            # Update the canvas
            offscreen_canvas = self.matrix.SwapOnVSync(offscreen_canvas)

# Main function
if __name__ == "__main__":
    waveform = WaveformAnimation()
    if (not waveform.process()):
        waveform.print_help()
