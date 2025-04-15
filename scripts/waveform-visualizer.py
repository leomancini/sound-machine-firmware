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
        self.ready_message = "READY"
        self.show_ready_message = False
        self.ready_message_time = 0
        self.ready_message_duration = 5  # Show ready message for 5 seconds
        self.show_loading_message = True  # Start with loading message
        self.loading_dots = 0  # For loading animation
        self.last_dot_update = 0  # For loading animation timing
        
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
        
        for i, char in enumerate(text):
            if char in font:
                # Calculate position with horizontal flip
                char_x = x - i * (char_width + char_spacing)
                
                for row in range(char_height):
                    for col in range(char_width):
                        if font[char][row][col] == 1:
                            # Flip vertically by calculating the flipped y position
                            flipped_y = y + (char_height - 1 - row)
                            canvas.SetPixel(char_x + col, flipped_y, color[0], color[1], color[2])

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
        
        last_scheme = None
        
        # Fixed brightness value for all colors
        BRIGHTNESS = 180  # Value between 0-255, where 255 is maximum brightness
        
        while True:
            offscreen_canvas.Clear()
            self.usleep(50 * 1000)  # Slightly slower update for smoother animation
            time_var += 0.2
            
            # Get the current color scheme (thread-safe)
            with self.lock:
                current_scheme = self.color_scheme
                has_tag_been_scanned = self.tag_scanned
                show_ready = self.show_ready_message
                ready_time = self.ready_message_time
                show_loading = self.show_loading_message
                loading_dots = self.loading_dots
                last_dot_update = self.last_dot_update
            
            # Update loading dots animation
            current_time = time.time()
            if show_loading and current_time - last_dot_update > 0.5:
                with self.lock:
                    self.loading_dots = (self.loading_dots + 1) % 4
                    self.last_dot_update = current_time
            
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
                # Calculate position to center the text
                text = "LOADING" + "." * loading_dots
                text_width = len(text) * 6  # 5 pixels wide + 1 pixel spacing
                text_x = (width - text_width) // 2
                text_y = (height - 7) // 2  # 7 pixels high
                
                # Draw the text in white
                self.draw_text(offscreen_canvas, text, text_x, text_y, (255, 255, 255))
            
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
