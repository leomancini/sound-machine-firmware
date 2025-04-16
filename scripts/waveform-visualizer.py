#!/usr/bin/env python3
import os
import sys
import json
import time
import threading
import numpy as np
from samplebase import SampleBase
from rgbmatrix import graphics
from PIL import Image, ImageDraw

from waveform_cache import waveform_cache

class WaveformAnimation(SampleBase):
    def __init__(self, *args, **kwargs):
        super(WaveformAnimation, self).__init__(*args, **kwargs)
        self.fifo_path = "/tmp/rfid_pipe"
        self.audio_fifo_path = "/tmp/audio_pipe"
        self.ready_pipe_path = "/tmp/ready_pipe"
        
        # Create FIFO pipes if they don't exist
        if not os.path.exists(self.fifo_path):
            os.mkfifo(self.fifo_path)
        if not os.path.exists(self.audio_fifo_path):
            os.mkfifo(self.audio_fifo_path)
        if not os.path.exists(self.ready_pipe_path):
            os.mkfifo(self.ready_pipe_path)
            
        self.current_tag = None
        self.is_playing = False
        self.waveform_data = None
        self.waveform_position = 0
        
        # Start RFID reader thread
        self.rfid_thread = threading.Thread(target=self.rfid_reader)
        self.rfid_thread.daemon = True
        self.rfid_thread.start()
        
        # Start ready signal reader thread
        self.ready_thread = threading.Thread(target=self.ready_reader)
        self.ready_thread.daemon = True
        self.ready_thread.start()
        
    def rfid_reader(self):
        """Read RFID tags from the FIFO pipe and forward to audio player."""
        while True:
            try:
                with open(self.fifo_path, 'r') as fifo:
                    tag_id = fifo.read().strip()
                    if tag_id:
                        # Forward to audio player
                        with open(self.audio_fifo_path, 'w') as audio_fifo:
                            audio_fifo.write(tag_id)
                        
                        # Update current tag and waveform data
                        self.current_tag = tag_id
                        self.waveform_data = waveform_cache.get_waveform(tag_id)
                        self.waveform_position = 0
                        self.is_playing = True
            except Exception as e:
                print(f"Error in RFID reader: {e}")
                time.sleep(0.1)
                
    def ready_reader(self):
        """Read ready signals from the FIFO pipe."""
        while True:
            try:
                with open(self.ready_pipe_path, 'r') as fifo:
                    signal = fifo.read().strip()
                    if signal == "ready":
                        self.is_playing = False
                        self.current_tag = None
                        self.waveform_data = None
                        self.waveform_position = 0
            except Exception as e:
                print(f"Error in ready reader: {e}")
                time.sleep(0.1)
                
    def run(self):
        """Main animation loop."""
        offset_canvas = self.matrix.CreateFrameCanvas()
        
        while True:
            if self.is_playing and self.waveform_data:
                # Clear the canvas
                offset_canvas.Clear()
                
                # Draw the waveform
                width = self.matrix.width
                height = self.matrix.height
                center_y = height // 2
                
                # Calculate how many samples to display based on the width
                samples_per_pixel = max(1, len(self.waveform_data) // width)
                
                for x in range(width):
                    # Calculate the sample index for this x position
                    sample_idx = (self.waveform_position + x * samples_per_pixel) % len(self.waveform_data)
                    
                    # Get the waveform value and scale it to the display height
                    value = self.waveform_data[sample_idx]
                    y_offset = int((value / 15.0) * (height / 2))  # Scale to half height
                    
                    # Draw a vertical line for this sample
                    for y in range(height):
                        if abs(y - center_y) <= y_offset:
                            # Use different colors for positive and negative parts
                            if y < center_y:
                                color = (0, 255, 0)  # Green for negative
                            else:
                                color = (0, 0, 255)  # Blue for positive
                            offset_canvas.SetPixel(x, y, *color)
                
                # Update the display
                offset_canvas = self.matrix.SwapOnVSync(offset_canvas)
                
                # Advance the waveform position
                self.waveform_position = (self.waveform_position + 1) % len(self.waveform_data)
                
            else:
                # When not playing, show a simple idle animation
                offset_canvas.Clear()
                for x in range(self.matrix.width):
                    for y in range(self.matrix.height):
                        offset_canvas.SetPixel(x, y, 0, 0, 0)
                offset_canvas = self.matrix.SwapOnVSync(offset_canvas)
            
            time.sleep(0.05)  # Control animation speed

if __name__ == "__main__":
    waveform = WaveformAnimation()
    if (not waveform.process()):
        waveform.print_help()
