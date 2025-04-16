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
        
        # Test colors with reduced brightness
        self.colors = [
            (64, 0, 0),     # Dim Red
            (0, 64, 0),     # Dim Green
            (0, 0, 64),     # Dim Blue
            (64, 64, 64),   # Dim White
            (32, 32, 32),   # Very Dim White
            (16, 16, 16),   # Extremely Dim White
        ]
        
        # Rectangle parameters
        self.rect_width = 16
        self.rect_height = 16
        self.rect_spacing = 0
        
        # These will be initialized in run()
        self.cols = None
        self.rows = None
        
        # Channel combinations to try
        self.channel_combinations = [
            ("RGB", lambda r, g, b: (r, g, b)),
            ("RBG", lambda r, g, b: (r, b, g)),
            ("GRB", lambda r, g, b: (g, r, b)),
            ("GBR", lambda r, g, b: (g, b, r)),
            ("BRG", lambda r, g, b: (b, r, g)),
            ("BGR", lambda r, g, b: (b, g, r)),
        ]
        self.current_combination = 0
    
    def draw_rectangle(self, canvas, x, y, width, height, color):
        """Draw a rectangle with the given color."""
        r, g, b = color
        # Get the current channel combination
        combo_name, combo_func = self.channel_combinations[self.current_combination]
        r_out, g_out, b_out = combo_func(r, g, b)
        
        print(f"Setting pixels with values: R={r_out}, G={g_out}, B={b_out}")
        
        for i in range(x, x + width):
            for j in range(y, y + height):
                canvas.SetPixel(i, j, r_out, g_out, b_out)
    
    def run(self):
        offscreen_canvas = self.matrix.CreateFrameCanvas()
        height = self.matrix.height
        width = self.matrix.width
        
        print(f"Matrix dimensions: {width}x{height}")
        print(f"RGB Sequence: {self.args.led_rgb_sequence}")
        print(f"Hardware mapping: {self.args.led_gpio_mapping}")
        print(f"Chain length: {self.args.led_chain}")
        print(f"Parallel chains: {self.args.led_parallel}")
        print(f"Brightness: {self.args.led_brightness}")
        
        # Initialize grid dimensions
        self.cols = width // (self.rect_width + self.rect_spacing)
        self.rows = height // (self.rect_height + self.rect_spacing)
        
        print("\nColor test display active. Press CTRL-C to exit.")
        print("Testing colors in this order:")
        for i, color in enumerate(self.colors):
            print(f"  {i+1}. RGB({color[0]}, {color[1]}, {color[2]})")
        
        print("\nIf colors are not displaying correctly, try:")
        print("1. Reducing brightness further with --led-brightness=50")
        print("2. Ensuring proper power supply (5V, 4A minimum)")
        print("3. Using shorter, thicker power cables")
        print("4. Adding capacitors to the power supply")
        
        try:
            while True:
                # Get current combination name
                combo_name, _ = self.channel_combinations[self.current_combination]
                print(f"\nTrying channel combination: {combo_name}")
                
                # Clear the canvas
                offscreen_canvas.Clear()
                
                # Draw a test pattern with each color
                for i, color in enumerate(self.colors):
                    x = i * self.rect_width
                    y = 0
                    self.draw_rectangle(offscreen_canvas, x, y, self.rect_width, self.rect_height, color)
                
                # Update the display
                offscreen_canvas = self.matrix.SwapOnVSync(offscreen_canvas)
                
                # Wait for 10 seconds before trying next combination
                print("Waiting 10 seconds...")
                time.sleep(10)
                
                # Move to next combination
                self.current_combination = (self.current_combination + 1) % len(self.channel_combinations)
                
        except KeyboardInterrupt:
            print("Exiting color test")

# Main function
if __name__ == "__main__":
    color_test = ColorTest()
    if not color_test.process():
        color_test.print_help() 