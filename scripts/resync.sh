#!/bin/bash

# Set the base directory
BASE_DIR=~/sound-machine-firmware/scripts

# Change to the base directory first
cd $BASE_DIR || {
    echo "Error: Could not change to directory $BASE_DIR"
    exit 1
}

echo "Starting resync process..."
echo "This will update all sounds from the remote server."

# Kill any existing audio-player screen session if it exists
screen -X -S audio-player quit > /dev/null 2>&1

# Start the audio player with resync flag
echo "Starting Audio Player with resync in a screen session..."
screen -dmS audio-player bash -c "cd $BASE_DIR && sudo python audio-player.py --resync --force-update --sync-interval=60 --max-downloads=10; exec bash"

echo "Resync process started in a screen session."
echo ""
echo "To view the resync progress, use:"
echo "  screen -r audio-player"
echo ""
echo "While in a screen session, press Ctrl+a then d to detach."
echo "To list all running screen sessions: screen -ls" 