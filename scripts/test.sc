var gAbsoluteOutputWavPath = "/tmp/_sctemp/MySound_attempt_1.wav";
var gRecipeDuration = 3.0; // Total duration for recording & envelope
var gEffectName = "MySound";

(
    Routine { // Wrap entire logic in a top-level Routine
        var p_freq = 440.0;
        var p_amp = 0.2;
        var p_attack = 0.05;
        var p_release = 0.8;
        var p_sustain;
        var server;

        p_sustain = max(0.001, gRecipeDuration - p_attack - p_release);
        server = Server.default;

        // Ensure sclang waits for the server (started by Python) to be ready
        server.waitForBoot {
            "SC_LOG: Server booted or was already running.".postln;

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
            }).add;
            "SC_LOG: SynthDef added.".postln;

            // Inner Routine for recording
            Routine {
                var targetSampleRate = 48000;

                server.recChannels = 1;
                server.recHeaderFormat = "WAV";
                server.recSampleFormat = "float";
                server.recBufSize = targetSampleRate.nextPowerOfTwo;

                "SC_LOG: Preparing for record: ".post; gAbsoluteOutputWavPath.postln;
                server.prepareForRecord(gAbsoluteOutputWavPath, 1);
                server.sync;
                "SC_LOG: Starting record.".postln;
                server.record;
                server.sync; // Ensure record command is processed

                "SC_LOG: Playing Synth.".postln;
                Synth(gEffectName ++ "_SynthDef", [
                    \masterAmp: p_amp,
                    \freq: p_freq,
                    \attackTime: p_attack,
                    \sustainTime: p_sustain,
                    \releaseTime: p_release
                ]);

                "SC_LOG: Waiting for recipe duration: ".post; gRecipeDuration.postln;
                gRecipeDuration.wait;

                "SC_LOG: Stopping recording.".postln;
                server.stopRecording;
                server.sync; // Ensure stopRecording is processed
                ("SC_LOG: Done recording: " ++ gAbsoluteOutputWavPath).postln;

                (0.1).wait; // Short delay for messages
                "SC_LOG: Script finished. Waiting for Python to terminate sclang.".postln;
                // 0.exit; // Python will terminate sclang via process management
            }.play(AppClock);
        }; // End of server.waitForBoot block
    }.play(AppClock); // Play the top-level Routine
); // Terminate the main expression block with a semicolon

// Add a ready signal for Python to detect
"Phonosyne SuperCollider script ready".postln;
