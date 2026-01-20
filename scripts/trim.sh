#!/bin/bash
# Trims silence from the beginning and end of all .wav files in a directory.
# Usage: ./scripts/trim.sh ./output/some-collection

if [ -z "$1" ]; then
    echo "Usage: $0 <directory>"
    exit 1
fi

find "$1" -type f -name "*.wav" -exec python ./scripts/phonosyne.py trim {} {} \;
