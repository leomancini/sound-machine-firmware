#!/usr/bin/env python3
from samplebase import SampleBase
import time
import random

class ColorTest(SampleBase):
    def __init__(self, *args, **kwargs):
        super(ColorTest, self).__init__(*args, **kwargs)
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
        
        # Calculate how many rectangles we can fit
        self.rect_width = 4
        self.rect_height = 4
        self.rect_spacing = 1
        
        # Calculate grid dimensions
        self.cols = self.matrix.width // (self.rect_width + self.rect_spacing)
        self.rows = self.matrix.height // (self.rect_height + self.rect_spacing)
        
        # Shuffle colors to make the display more interesting
        random.shuffle(self.colors)
        
        # Ensure we have enough colors for all rectangles
        while len(self.colors) < self.cols * self.rows:
            # Generate random colors if needed
            self.colors.append((
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255)
            ))
    
    def draw_rectangle(self, canvas, x, y, width, height, color):
        """Draw a rectangle with the given color."""
        for i in range(x, x + width):
            for j in range(y, y + height):
                canvas.SetPixel(i, j, color[0], color[1], color[2])
    
    def run(self):
        offscreen_canvas = self.matrix.CreateFrameCanvas()
        
        # Draw all color rectangles
        color_index = 0
        for row in range(self.rows):
            for col in range(self.cols):
                if color_index < len(self.colors):
                    x = col * (self.rect_width + self.rect_spacing)
                    y = row * (self.rect_height + self.rect_spacing)
                    self.draw_rectangle(
                        offscreen_canvas, 
                        x, 
                        y, 
                        self.rect_width, 
                        self.rect_height, 
                        self.colors[color_index]
                    )
                    color_index += 1
        
        # Update the display
        offscreen_canvas = self.matrix.SwapOnVSync(offscreen_canvas)
        
        # Keep the display on for a while
        print("Color test display active. Press CTRL-C to exit.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Exiting color test")

# Main function
if __name__ == "__main__":
    color_test = ColorTest()
    if (not color_test.process()):
        color_test.print_help() 