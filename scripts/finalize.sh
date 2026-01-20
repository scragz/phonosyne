find $1 -type f -name "*.wav" -exec python ./scripts/phonosyne.py master {} {} \;

# lubadh is f32
find $1 -type f -name "*.wav" -exec sh -c 'for f; do echo "Converting $f"; ffmpeg -i "$f" -c:a pcm_f32le -f wav -y "$f.tmp" && mv "$f.tmp" "$f"; done' _ {} \;

# arbhar is s24
# find $1 -type f -name "A*.wav" -exec sh -c 'for f; do echo "Converting $f"; ffmpeg -i "$f" -c:a pcm_s24le -f wav -y "$f.tmp" && mv "$f.tmp" "$f"; done' _ {} \;
