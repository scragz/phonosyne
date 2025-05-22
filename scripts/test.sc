var gAbsoluteOutputWavPath = "/tmp/_sctemp/MySound_attempt_1.wav";
var gRecipeDuration = 3.0; // Total duration for recording & envelope
var gEffectName = "MySound";

(
    Routine { // Wrap entire logic in a top-level Routine
        var p_freq = 440.0;
        var p_amp = 0.2;
        var p_attack = 0.05;    // Attack segment duration
        var p_release = 0.8;   // Release segment duration

        var p_sustain;
        var server;

        // Calculate sustain segment duration to make total envelope duration = gRecipeDuration
        p_sustain = max(0.001, gRecipeDuration - p_attack - p_release); // ensure positive

        server = Server.default; // Use \'Server.default\' for clarity, often aliased to \'s\'

        // Ensure server is running before proceeding
        if (server.serverRunning.not) {
            "SC: Server not running, attempting to boot...".postln;
            server.bootSync; // Boot and wait for completion - now inside a Routine
            "SC: Server booted.".postln;
        } {
            "SC: Server already running.".postln;
        };

        SynthDef(gEffectName ++ "_SynthDef", { |outBus = 0, gate = 1, masterAmp = 0.1, freq = 440, attackTime = 0.01, sustainTime = 1.0, releaseTime = 0.5|
            var signal, envelope;
            envelope = EnvGen.kr(
                Env.new([0, 1, 1, 0], [attackTime, sustainTime, releaseTime], curve: -4.0),
                gate,
                levelScale: masterAmp,
                doneAction: Done.freeSelf
            );
            signal = SinOsc.ar(freq);
            signal = signal * envelope;
            signal = signal.tanh; // MANDATORY tanh
            Out.ar(outBus, signal);
        }).add; // This now happens after server boot check

        // SynthDef.add is blocking on local server, no server.sync needed here outside a Routine.

        // This inner Routine for recording remains, and will be scheduled correctly
        // as part of the outer Routine\'s execution flow.
        Routine {
            var targetSampleRate = 48000; // Define intended sample rate

            // Set server\'s recorder properties before calling prepareForRecord
            server.recChannels = 1;
            server.recHeaderFormat = "WAV";
            server.recSampleFormat = "float";
            server.recBufSize = targetSampleRate.nextPowerOfTwo; // e.g., 65536 for 48kHz

            // Corrected prepareForRecord call
            server.prepareForRecord(gAbsoluteOutputWavPath, 1); // path, numChannels
            server.sync;
            server.record;
            server.sync;

            Synth(gEffectName ++ "_SynthDef", [
                \masterAmp: p_amp,
                \freq: p_freq,
                \attackTime: p_attack,
                \sustainTime: p_sustain, // Pass the calculated sustain segment duration
                \releaseTime: p_release
            ]);

            // Wait for the total recipe duration, which matches the envelope\'s total duration
            gRecipeDuration.wait;

            server.stopRecording;
            server.sync;
            ("SC: Done: " ++ gAbsoluteOutputWavPath).postln;

            // Quit sclang after a short delay to allow messages to flush
            (0.1).wait;
            "SC: Script finished. Quitting sclang.".postln;
            0.exit;
        }.play(AppClock); // This inner routine is played on AppClock as before

    }.play(AppClock); // Play the new top-level Routine
)
