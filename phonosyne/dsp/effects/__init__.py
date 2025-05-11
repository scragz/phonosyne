# filepath: /Users/scragz/Projects/phonosyne/phonosyne/dsp/effects/__init__.py
from .autowah import apply_autowah
from .chorus import apply_chorus
from .compressor import apply_compressor
from .delay import apply_delay
from .distortion import apply_distortion
from .dub_echo import apply_dub_echo
from .echo import apply_echo
from .flanger import apply_flanger
from .fuzz import apply_fuzz
from .long_reverb import apply_long_reverb
from .noise_gate import apply_noise_gate
from .overdrive import apply_overdrive
from .particle import apply_particle
from .phaser import apply_phaser
from .rainbow_machine import apply_rainbow_machine
from .short_reverb import apply_short_reverb
from .tremolo import apply_tremolo
from .vibrato import apply_vibrato

__all__ = [
    "apply_short_reverb",
    "apply_long_reverb",
    "apply_echo",
    "apply_dub_echo",
    "apply_delay",
    "apply_chorus",
    "apply_flanger",
    "apply_phaser",
    "apply_compressor",
    "apply_tremolo",
    "apply_vibrato",
    "apply_noise_gate",
    "apply_autowah",
    "apply_distortion",
    "apply_overdrive",
    "apply_fuzz",
    "apply_rainbow_machine",
    "apply_particle",
]
