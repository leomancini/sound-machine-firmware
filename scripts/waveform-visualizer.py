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
            
        # Flag to indicate whether a tag has been scanned
        self.tag_scanned = False
        
        # Dictionary to store color information for each tag
        self.tag_colors = {}
        
        # Load all color information during initialization
        self.load_all_tag_colors()
        
        # Color transition variables
        # Adjust white color to account for LED matrix color balance
        self.current_color = [200, 200, 255]  # Slightly blue-tinted white
        self.target_color = [200, 200, 255]  # Slightly blue-tinted white
        self.color_transition_speed = 0.1  # Speed of color transition (0-1)
        self.last_color_change_time = 0
        self.color_change_cooldown = 0.5  # Seconds to wait before allowing another color change
            
        print("Starting in grey mode. Waiting for RFID tags...")
        print("  - Tags with a manifest file will use their custom color")
        print("  - Any tag without a manifest will display in GREY")
        
        # Debug: Check which manifest files exist at startup
        print("\nChecking for manifest files in sounds directory...")
        if os.path.exists(self.sounds_dir):
            for tag_id in os.listdir(self.sounds_dir):
                tag_dir = os.path.join(self.sounds_dir, tag_id)
                manifest_path = os.path.join(tag_dir, "manifest.json")
                if os.path.exists(manifest_path):
                    try:
                        with open(manifest_path, 'r', encoding='utf-8') as f:
                            manifest = json.loads(f.read().strip())
                            color = manifest.get('color', None)
                            title = manifest.get('title', 'Unknown')
                            print(f"Found manifest for tag {tag_id}: {title} (Color: {color})")
                    except Exception as e:
                        print(f"Error reading manifest for tag {tag_id}: {e}")
                else:
                    print(f"No manifest found for tag {tag_id}")
        else:
            print(f"Sounds directory not found: {self.sounds_dir}")
        print("")  # Add a blank line after the manifest check
        
        self.custom_color = None  # Store custom color from manifest

    def load_all_tag_colors(self):
        """Load color information for all tags during initialization."""
        print("Loading color information for all tags...")
        if not os.path.exists(self.sounds_dir):
            print(f"Sounds directory not found: {self.sounds_dir}")
            return
            
        try:
            for tag_id in os.listdir(self.sounds_dir):
                tag_dir = os.path.join(self.sounds_dir, tag_id)
                if os.path.isdir(tag_dir) and tag_id.isdigit():
                    manifest_path = os.path.join(tag_dir, "manifest.json")
                    if os.path.exists(manifest_path):
                        try:
                            with open(manifest_path, 'r', encoding='utf-8') as f:
                                manifest_content = f.read().strip()
                                manifest = json.loads(manifest_content)
                                if 'color' in manifest:
                                    color = manifest['color']
                                    if isinstance(color, list) and len(color) == 3:
                                        # Ensure all values are integers and within range
                                        r = max(0, min(255, int(color[0])))
                                        g = max(0, min(255, int(color[1])))
                                        b = max(0, min(255, int(color[2])))
                                        self.tag_colors[tag_id] = [r, g, b]
                                        print(f"Loaded color for tag {tag_id}: R={r}, G={g}, B={b}")
                        except Exception as e:
                            print(f"Error loading color for tag {tag_id}: {e}")
        except Exception as e:
            print(f"Error loading tag colors: {e}")
            
        print(f"Loaded color information for {len(self.tag_colors)} tags")

    def get_color_from_manifest(self, tag_id):
        """Get color from the cached tag colors dictionary."""
        # Strip any leading/trailing whitespace from tag_id
        tag_id = tag_id.strip()
        
        # Check if we have a cached color for this tag
        if tag_id in self.tag_colors:
            color = self.tag_colors[tag_id]
            print(f"Using cached color for tag {tag_id}: {color}")
            return color
            
        # If not in cache, try to load it from the manifest file
        try:
            # Strip any leading/trailing whitespace from tag_id
            tag_id = tag_id.strip()
            
            manifest_path = os.path.join(self.sounds_dir, tag_id, "manifest.json")
            print(f"DEBUG: Looking for manifest at: {manifest_path}")
            
            if os.path.exists(manifest_path):
                print(f"DEBUG: Manifest file exists for tag {tag_id}")
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest_content = f.read()
                    print(f"DEBUG: Raw manifest content: {manifest_content}")
                    # Try to clean the content
                    manifest_content = manifest_content.strip()
                    print(f"DEBUG: Cleaned manifest content: {manifest_content}")
                    manifest = json.loads(manifest_content)
                    if 'color' in manifest:
                        color = manifest['color']
                        print(f"DEBUG: Found color in manifest: {color}, type: {type(color)}")
                        
                        # Ensure color is in the correct format [r, g, b]
                        if isinstance(color, list) and len(color) == 3:
                            # Already in the correct format
                            print(f"DEBUG: Color is in correct format: {color}")
                            # Ensure all values are integers and within range
                            r = max(0, min(255, int(color[0])))
                            g = max(0, min(255, int(color[1])))
                            b = max(0, min(255, int(color[2])))
                            print(f"DEBUG: Returning color values: R={r}, G={g}, B={b}")
                            
                            # Cache the color for future use
                            self.tag_colors[tag_id] = [r, g, b]
                            
                            return [r, g, b]
            else:
                print(f"DEBUG: Manifest file does not exist at: {manifest_path}")
        except Exception as e:
            print(f"DEBUG: Error in get_color_from_manifest: {e}")
            import traceback
            traceback.print_exc()
        return None

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
                            
                            # Try to get color from cached tag colors
                            if tag_id in self.tag_colors:
                                print(f"DEBUG: Using cached color for tag: '{tag_id}'")
                                new_color = self.tag_colors[tag_id]
                                print(f"DEBUG: Found color for tag: {new_color}")
                                
                                # Set the target color for smooth transition
                                self.target_color = new_color
                                self.last_color_change_time = time.time()
                                print(f"DEBUG: Set target color to: {self.target_color}")
                            else:
                                # If not in cache, try to load it from the manifest file
                                custom_color = self.get_color_from_manifest(tag_id)
                                
                                if custom_color:
                                    print(f"DEBUG: Using custom color from manifest: {custom_color}")
                                    # Ensure the color values are integers
                                    new_color = [int(c) for c in custom_color]
                                    print(f"DEBUG: Set target color to: {new_color}")
                                    
                                    # Set the target color for smooth transition
                                    self.target_color = new_color
                                    self.last_color_change_time = time.time()
                                else:
                                    print(f"DEBUG: No manifest found for tag: '{tag_id}', setting to GREY")
                                    self.target_color = [200, 200, 255]  # Slightly blue-tinted white
                                    self.last_color_change_time = time.time()
                        
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
        
        # Debug flag to print color information
        debug_colors = True
        
        # Track the last color state to avoid repeating debug messages
        last_custom_color = None
        last_color_debug_time = 0
        color_debug_interval = 5  # Only print color debug messages every 5 seconds
        
        # Track if we're actually updating sounds
        updating_sounds = False
        last_progress_update_time = 0
        progress_timeout = 10  # Seconds to wait before assuming no sounds are being updated
        
        while True:
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
                target_color = self.target_color
                last_color_change_time = self.last_color_change_time
            
            # Check if ready message should be hidden
            if show_ready and time.time() - ready_time > self.ready_message_duration:
                with self.lock:
                    self.show_ready_message = False
            
            # Check if we're actually updating sounds
            current_time = time.time()
            if "Updating sound" in loading_message:
                updating_sounds = True
                last_progress_update_time = current_time
            elif current_time - last_progress_update_time > progress_timeout:
                updating_sounds = False
                with self.lock:
                    self.show_loading_message = False
            
            # Smooth color transition
            if current_time - last_color_change_time > self.color_change_cooldown:
                # Calculate the difference between current and target colors
                color_diff = [
                    target_color[0] - self.current_color[0],
                    target_color[1] - self.current_color[1],
                    target_color[2] - self.current_color[2]
                ]
                
                # Apply the transition
                if abs(color_diff[0]) > 1 or abs(color_diff[1]) > 1 or abs(color_diff[2]) > 1:
                    self.current_color = [
                        self.current_color[0] + color_diff[0] * self.color_transition_speed,
                        self.current_color[1] + color_diff[1] * self.color_transition_speed,
                        self.current_color[2] + color_diff[2] * self.color_transition_speed
                    ]
                    
                    # Ensure values are within valid range
                    self.current_color = [
                        max(0, min(255, int(self.current_color[0]))),
                        max(0, min(255, int(self.current_color[1]))),
                        max(0, min(255, int(self.current_color[2])))
                    ]
                    
                    # Print debug info occasionally
                    if current_time - last_color_debug_time >= color_debug_interval:
                        print(f"DEBUG: Transitioning color to: R={self.current_color[0]}, G={self.current_color[1]}, B={self.current_color[2]}")
                        last_color_debug_time = current_time
            
            # Set colors based on the current color
            red = self.current_color[0]
            green = self.current_color[1]
            blue = self.current_color[2]
            
            # Only print debug message if color has changed or enough time has passed
            current_time = time.time()
            if (self.current_color != last_custom_color or 
                (current_time - last_color_debug_time) >= color_debug_interval):
                print(f"DEBUG: Drawing waveform with color: R={red}, G={green}, B={blue}")
                last_custom_color = self.current_color.copy()  # Make a copy to avoid reference issues
                last_color_debug_time = current_time
            
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
                        # Set the pixel with the current color
                        offscreen_canvas.SetPixel(x, y, red, green, blue)
            else:
                # Before any tag is scanned, just draw a single horizontal gray line
                mid_point = height // 2
                for x in range(width):
                    offscreen_canvas.SetPixel(x, mid_point, BRIGHTNESS, BRIGHTNESS, BRIGHTNESS)
            
            # Draw loading message if needed
            if show_loading:
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
