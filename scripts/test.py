import asyncio
import random
import traceback  # For detailed error logging
from pathlib import Path

import supriya
import supriya.contexts  # Specifically for Score
import supriya.enums  # For HeaderFormat, SampleFormat, DoneAction
import supriya.ugens  # For UGens

# --- Values embedded by Phonosyne CompilerAgent based on recipe_json ---
duration = 5.0  # Target duration of the sound event
effect_name = "MyEffect"  # From recipe, used for SynthDef naming
output_filename = "output.wav"  # This will be injected by the execution environment

# --- Audio config ---
SR = 48000
CHANNELS = 1  # 1 for mono, 2 for stereo

# --- File and naming ---
unique_id_for_synthdef = random.randint(0, 100000)  # Ensures unique SynthDef name

# --- SynthDef Default Parameter Values ---
# These are the *default* values for the SynthDef's arguments.
# The CompilerAgent maps recipe parameters to these.
initial_frequency_val = 440.0
initial_amplitude_val = 0.1
attack_time_val = 0.02  # For default envelope shape
release_time_val = 0.1  # For default envelope shape
# ... other SynthDef default parameters as needed ...

# --- Score Instance Parameter Values ---
# These are the *specific* values for *this* sound instance when played on the Score.
frequency_to_play_val = 220.0
amplitude_to_play_val = 0.25
# ... other instance-specific parameters for the score event ...
# --- End Embedded Values ---


# 'output_filename' (string path) is injected by the PythonCodeExecutionTool execution environment.
# We'll convert it to a Path object where needed.


async def generate_sound():
    try:
        # output_path = Path(output_filename) # Use the injected variable
        # For testing directly if output_filename isn't injected yet:
        output_path = Path(output_filename)
        if "output_filename" in globals():
            output_path = Path(globals()["output_filename"])

        print(f"INFO: Target output filename: {output_path}")
        print(
            f"INFO: Sound duration: {duration}s, Sample Rate: {SR}, Channels: {CHANNELS}"
        )

        # --- SynthDef Creation ---
        # Uses 'initial_<param>_val' for SynthDef parameter defaults
        # and 'attack_time_val', 'release_time_val' for envelope structure.

        synthdef_name = f"synth_{effect_name}_{unique_id_for_synthdef}"

        with supriya.SynthDefBuilder(
            out_bus=0,  # Output will be to bus 0 for Score rendering
            # Define SynthDef parameters. Their default/initial values:
            frequency=initial_frequency_val,
            amplitude=initial_amplitude_val,
            # Add other parameters required by the 'effect_name'
            # e.g., filter_cutoff=1200.0
        ) as builder:
            gate_signal = supriya.ugens.Line.kr(
                start=1,
                stop=0,
                duration=duration,
                done_action=supriya.enums.DoneAction.FREE_SYNTH,  # Essential!
            )

            # Define the envelope shape to go from 0 to 1 and back to 0.
            # The actual output level will be controlled by builder["amplitude"] via EnvGen's level_scale.
            # from supriya.ugens.envelopes import Envelope # Ensure this import is at the top of your script
            simple_envelope_shape = supriya.ugens.Envelope.percussive(
                attack_time=max(0.001, attack_time_val),
                release_time=max(
                    0.001,
                    duration - attack_time_val if duration > attack_time_val else 0.001,
                ),
                amplitude=1.0,  # Envelope shape peaks at 1.0
                curve=-4.0,
            )
            # If duration is very short, an ASR or ADSR might be more robust
            if duration > (attack_time_val + release_time_val):
                simple_envelope_shape = supriya.ugens.Envelope.asr(
                    attack_time=max(0.001, attack_time_val),
                    sustain=1.0,  # Sustain at peak of shape
                    release_time=max(0.001, release_time_val),
                    curve=-4.0,
                )

            env_gen = supriya.ugens.EnvGen.kr(
                envelope=simple_envelope_shape,
                gate=gate_signal,
                level_scale=builder[
                    "amplitude"
                ],  # Instance amplitude scales the 0-1 shape
                done_action=supriya.enums.DoneAction.NOTHING,  # Line.kr handles freeing
            )

            source_signal = supriya.ugens.SinOsc.ar(frequency=builder["frequency"])
            applied_envelope_signal = (
                source_signal * env_gen
            )  # Amplitude is now correctly scaled

            # ... rest of your signal chain ...
            processed_signal = applied_envelope_signal.tanh()

            if CHANNELS == 2:
                processed_signal = supriya.ugens.Pan2.ar(
                    source=processed_signal, position=0
                )

            supriya.ugens.Out.ar(bus=builder["out_bus"], source=processed_signal)

        synth_def_compiled = builder.build(name=synthdef_name)
        # print(f"INFO: SynthDef '{synthdef_name}' built.")

        # --- Score Creation and Rendering ---
        score = supriya.contexts.Score(
            # options=supriya.Options(sample_rate=SR) # If options need to be specific
        )

        # Arguments for this specific synth instance on the score
        # Uses '..._to_play_val' for instance-specific values.
        synth_instance_args_for_score = {
            "frequency": frequency_to_play_val,
            "amplitude": amplitude_to_play_val,
            # Add other instance-specific synth arguments here
        }

        with score.at(0):  # Add synth at the beginning of the score
            score.add_synth(
                synthdef=synth_def_compiled,
                duration=duration,  # The actual duration the synth will play in the score
                **synth_instance_args_for_score,
            )

        # print(f"INFO: Starting Score rendering to {output_path} for {duration}s.")

        # Parameters for Score.render() from your nonrealtime.py
        rendered_file_path, exit_code = await score.render(
            output_file_path=output_path,
            duration=duration,  # Render the score for this total duration
            sample_rate=float(SR),
            header_format=supriya.HeaderFormat.WAV,  # e.g., AIFF, WAV
            sample_format=supriya.SampleFormat.FLOAT,  # e.g., INT24, FLOAT
            # input_file_path=None, # Optional: if rendering with an input audio file
            # render_directory_path=None, # Optional: for custom temp render location
            # suppress_output=False # Set to True to not save the file (e.g., for benchmarking)
        )

        if exit_code == 0:
            # print(f"INFO: Score successfully rendered to {rendered_file_path}")
            pass
        else:
            print(f"ERROR: Score rendering failed with scsynth exit code: {exit_code}")
            # Attempt to print scsynth error output if available (depends on protocol details)
            # This part is speculative as direct error text access wasn't in nonrealtime.py snippet
            # if hasattr(score, "_last_scsynth_process_protocol") and \
            #    hasattr(score._last_scsynth_process_protocol, "error_text"):
            # print(f"scsynth error: {score._last_scsynth_process_protocol.error_text}")

    except Exception as e:
        print(f"ERROR: An error occurred during sound generation or rendering:")
        print(traceback.format_exc())
        # Ensure a non-zero exit code or error signal if used in an automated system
        # For now, just printing the error.


# --- Script Execution ---
if __name__ == "__main__":
    # This block is for direct execution testing.
    # Phonosyne CompilerAgent will likely embed values and then trigger execution.

    # --- Example Embedded Values for direct testing ---
    effect_name = "TanhSine"
    duration = 2.0
    SR = 48000
    CHANNELS = 1
    output_filename_str = "phonosyne_tanh_sine_test.wav"  # For direct script run
    unique_id_for_synthdef = random.randint(0, 100000)

    initial_frequency_val = 440.0
    initial_amplitude_val = 0.2
    attack_time_val = 0.05
    release_time_val = 0.5

    frequency_to_play_val = 880.0
    amplitude_to_play_val = 0.5
    # ---

    try:
        asyncio.run(generate_sound())
    except RuntimeError as e:
        if "asyncio.run() cannot be called from a running event loop" in str(e):
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = loop.create_task(generate_sound())
                # In a more complex application, you'd await task or handle it.
            else:  # Should not happen if asyncio.run failed due to already running loop
                loop.run_until_complete(generate_sound())
        else:
            raise e
    except Exception as e:
        print(f"CRITICAL ERROR in script execution: {e}")
        print(traceback.format_exc())
