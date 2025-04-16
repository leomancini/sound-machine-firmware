#!/usr/bin/env python3
from samplebase import SampleBase
import time
import random
import threading
import os

class ColorTest(SampleBase):
    def __init__(self, *args, **kwargs):
        super(ColorTest, self).__init__(*args, **kwargs)
        self.lock = threading.Lock()
        
        # Colors to display
        self.colors = [
            # Primary colors
            (255, 0, 0),    # Red
            (0, 255, 0),    # Green
            (0, 0, 255),    # Blue
            
            # Secondary colors
            (255, 255, 0),  # Yellow
            (255, 0, 255),  # Magenta
            (0, 255, 255),  # Cyan
            
            # Tertiary colors
            (255, 128, 0),  # Orange
            (128, 0, 255),  # Purple
            (0, 255, 128),  # Teal
            
            # Grayscale
            (255, 255, 255), # White
            (192, 192, 192), # Silver
            (128, 128, 128), # Gray
            (64, 64, 64),    # Dark Gray
            (0, 0, 0),       # Black
            
            # Pastel colors
            (255, 182, 193), # Light Pink
            (173, 216, 230), # Light Blue
            (144, 238, 144), # Light Green
            
            # Bright colors
            (255, 20, 147),  # Deep Pink
            (0, 191, 255),   # Deep Sky Blue
            (50, 205, 50),   # Lime Green
        ]
        
        # Shuffle colors to make the display more interesting
        random.shuffle(self.colors)
        
        # Animation parameters
        self.animation_speed = 0.5  # Speed of color transitions
        self.current_color_index = 0
        self.next_color_index = 1
        self.transition_progress = 0.0
        
        # Rectangle parameters
        self.rect_width = 4
        self.rect_height = 4
        self.rect_spacing = 1
        
        # These will be initialized in run()
        self.cols = None
        self.rows = None
    
    def draw_rectangle(self, canvas, x, y, width, height, color):
        """Draw a rectangle with the given color."""
        # For 2.5mm pitch 64x32 display, swap green and blue channels
        r, g, b = color
        for i in range(x, x + width):
            for j in range(y, y + height):
                canvas.SetPixel(i, j, r, b, g)  # Swapped g and b
    
    def interpolate_color(self, color1, color2, progress):
        """Interpolate between two colors based on progress (0.0 to 1.0)."""
        r = int(color1[0] * (1 - progress) + color2[0] * progress)
        g = int(color1[1] * (1 - progress) + color2[1] * progress)
        b = int(color1[2] * (1 - progress) + color2[2] * progress)
        return (r, g, b)
    
    def run(self):
        offscreen_canvas = self.matrix.CreateFrameCanvas()
        height = self.matrix.height
        width = self.matrix.width
        
        # Initialize grid dimensions now that we have the matrix
        self.cols = width // (self.rect_width + self.rect_spacing)
        self.rows = height // (self.rect_height + self.rect_spacing)
        
        # Ensure we have enough colors for all rectangles
        while len(self.colors) < self.cols * self.rows:
            # Generate random colors if needed
            self.colors.append((
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255)
            ))
        
        # Animation variables
        time_var = 0
        
        print("Color test display active. Press CTRL-C to exit.")
        try:
            while True:
                offscreen_canvas.Clear()
                self.usleep(50 * 1000)  # Slightly slower update for smoother animation
                time_var += 0.05
                
                # Update transition progress
                self.transition_progress += self.animation_speed * 0.05
                if self.transition_progress >= 1.0:
                    self.transition_progress = 0.0
                    self.current_color_index = self.next_color_index
                    self.next_color_index = (self.next_color_index + 1) % len(self.colors)
                
                # Draw all color rectangles
                color_index = 0
                for row in range(self.rows):
                    for col in range(self.cols):
                        if color_index < len(self.colors):
                            x = col * (self.rect_width + self.rect_spacing)
                            y = row * (self.rect_height + self.rect_spacing)
                            
                            # Get current and next color for this rectangle
                            current_color = self.colors[color_index]
                            next_color = self.colors[(color_index + 1) % len(self.colors)]
                            
                            # Interpolate between colors
                            color = self.interpolate_color(
                                current_color, 
                                next_color, 
                                self.transition_progress
                            )
                            
                            self.draw_rectangle(
                                offscreen_canvas, 
                                x, 
                                y, 
                                self.rect_width, 
                                self.rect_height, 
                                color
                            )
                            color_index += 1
                
                # Update the display
                offscreen_canvas = self.matrix.SwapOnVSync(offscreen_canvas)
                
        except KeyboardInterrupt:
            print("Exiting color test")

# Main function
if __name__ == "__main__":
    color_test = ColorTest()
    if not color_test.process():
        color_test.print_help() 