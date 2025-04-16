#!/bin/bash

# Set the base directory
#BASE_DIR=~/rpi-rgb-led-matrix/bindings/python/sound-machine
BASE_DIR=~/sound-machine-firmware/scripts

# Change to the base directory first
cd $BASE_DIR || {
    echo "Error: Could not change to directory $BASE_DIR"
    exit 1
}

# Check if screen is installed, if not, install it
if ! command -v screen &> /dev/null; then
    echo "screen is not installed. Installing now..."
    sudo apt-get update
    sudo apt-get install -y screen
    
    # Check if installation was successful
    if ! command -v screen &> /dev/null; then
        echo "Failed to install screen. Running scripts in background."
        sudo python rfid-reader.py > rfid.log 2>&1 &
        sudo python waveform-visualizer.py -m=adafruit-hat --led-rows=32 --led-cols=64 --led-slowdown-gpio=4 > visualizer.log 2>&1 &
        sudo python audio-player.py --max-downloads=10 > audio.log 2>&1 &
        echo "Scripts are running in background. Check log files for output."
        exit 0
    fi
fi

# Kill any existing screen sessions if they exist
screen -wipe > /dev/null 2>&1
screen -X -S rfid-reader quit > /dev/null 2>&1
screen -X -S waveform-visualizer quit > /dev/null 2>&1
screen -X -S audio-player quit > /dev/null 2>&1

# Start each program in its own separate screen session
echo "Starting RFID Reader in a screen session..."
screen -dmS rfid-reader bash -c "cd $BASE_DIR && sudo python rfid-reader.py; exec bash"

echo "Starting Waveform Visualizer in a screen session..."
screen -dmS waveform-visualizer bash -c "cd $BASE_DIR && sudo python waveform-visualizer.py -m=adafruit-hat --led-rows=32 --led-cols=64 --led-slowdown-gpio=4; exec bash"

echo "Starting Audio Player in a screen session..."
screen -dmS audio-player bash -c "cd $BASE_DIR && sudo python audio-player.py --sync-interval=60 --max-downloads=10; exec bash"

echo "All scripts are now running in separate screen sessions."
echo ""
echo "To view a session, use one of the following commands:"
echo "  screen -r rfid-reader"
echo "  screen -r waveform-visualizer"
echo "  screen -r audio-player"
echo ""
echo "While in a screen session, press Ctrl+a then d to detach."
echo "To list all running screen sessions: screen -ls"

