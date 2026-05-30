#!/bin/bash
cd ~/tts
PYTHON=$HOME/miniforge3/envs/tts2/bin/python

for char in male-young-minor male-mid-minor male-weathered-minor; do
  for i in 1 2 3 4; do
    echo "Locking: ${char}-${i}"
    $PYTHON lock-voice.py waterdeep-dragon-heist "${char}-${i}" --wav "website/waterdeep-dragon-heist/audio/voices/${char}_audition_${i}.wav" 2>&1 | grep -E "Saved|Done|Error"
  done
done
echo "All done."
