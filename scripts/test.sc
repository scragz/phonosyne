(
  "SCRIPT_DEBUG: TOP OF SCRIPT EXECUTION".postln; // ADDED FOR VERY EARLY DEBUG

  // Original gEffectName to define the SynthDef name consistently
  var gEffectName = "L3.1_deep_half_time_bass_drop_glides_down_from_a1_to_f_sharp0_with_pitch_envelope";
  var synthDefNameForThisScript = ("Synth_" ++ gEffectName).replace(" ", "_").replace(".", "_").replace("#", "Sharp");

  // Bass drop frequencies
  var freqStart = 55; // A1
  var freqEnd = 23.12; // F#0

  // Pitch envelope times
  var pitchEnvAttack = 0.2; // 200 ms sharp drop
  var pitchEnvDecay = 6.0; // slow decay to target pitch

  // Wavefolder drive modulation
  var wavefolderLfoFreq = 0.13;

  // Allpass delay parameters
  var delayTime = 0.08; // 80 ms
  var delayFeedback = 0.45;

  // Resonant filter center frequencies
  var resonzFreq1 = 110;
  var resonzFreq2 = 220;
  var resonzSweepRange = 0.08; // ±8%
  var resonzSweepSpeed = 0.1; // slow random walk speed

  // Sidechain ducking parameters
  var duckAmountDb = -6;
  var duckTime = 0.05; // 50 ms

  // Percussion parameters
  var clickAttack = 0.008; // 8 ms
  var clickDecay = 0.04; // 40 ms
  var clickHpfFreq = 3000;
  var clickHpfQ = 0.7;
  var ringModFreq = 55;
  var ringDepthMin = 0.3;
  var ringDepthMax = 0.7;

  // Echo parameters
  var echoDelayMin = 0.42;
  var echoDelayMax = 0.68;
  var echoFeedback = 0.38;
  var echoWetMin = 0.2;
  var echoWetMax = 0.6;
  var echoHpfFreq = 180;

  // Jitter parameters
  var jitterFreq = 0.1;
  var jitterAmount = 0.002;

  // Percussion dropout interval
  var dropoutInterval = 7.0;

  var currentSynth;
  var server = Server.default; // Assuming server is already booted by Python

  "SCRIPT_DEBUG: Variables declared. Setting NetAddr.langPort...".postln;
  NetAddr.langPort = 57120; // Ensure sclang listens on the default port for OSC
  "SCRIPT_DEBUG: NetAddr.langPort set to 57120.".postln;

  // Ensure server is running before adding SynthDef.
  // This might be redundant if Python guarantees server is up, but good for standalone testing.
  // server.waitForBoot {
  // "SCRIPT_DEBUG: Server booted (or was already running). Defining SynthDef...".postln;

  "SCRIPT_DEBUG: Defining SynthDef: %".format(synthDefNameForThisScript).postln;
  SynthDef(synthDefNameForThisScript, {
    |out = 0, recipeDurationArg = 10.0| // recipeDurationArg will be set by OSC message
    var bassOsc, pitchEnv, pitch, bassSig, wavefolderDrive, wavefolder, feedbackSig, resonz1, resonz2, resonzMix, sidechainEnv;
    var percussionEnv, percussionClick, percussionRingMod, percussionSig, percussionVelocity;
    var echoDelayTime, echoDelay, echoWet, echoSig, echoHpf, echoMix;
    var jitterPhase, jitterDelayTime, dropoutGate; // jitterDelayTime is defined but not used in original logic
    var sig, finalSig;

    // Pitch envelope: exponential from freqStart to freqEnd
    pitchEnv = EnvGen.kr(Env([freqStart, freqEnd], [pitchEnvAttack + pitchEnvDecay], 'exp'), doneAction: 0);
    pitch = pitchEnv;

    // Bass oscillator mix: 70% sine, 30% saw
    bassOsc = (SinOsc.ar(pitch) * 0.7) + (Saw.ar(pitch) * 0.3);

    // Wavefolder drive modulated by LFO
    wavefolderDrive = LFNoise0.kr(wavefolderLfoFreq).range(0.5, 1.5);
    wavefolder = Shaper.ar(VarSaw.ar(0, 0, 1), wavefolderDrive);

    // Feedback via AllpassC delays
    feedbackSig = AllpassC.ar(bassOsc + wavefolder, delayTime, delayTime, delayFeedback);

    // Resonz filters with slow random walk modulation
    resonz1 = Resonz.ar(feedbackSig, resonzFreq1 * (1 + LFNoise1.kr(resonzSweepSpeed).range(-resonzSweepRange, resonzSweepRange)), 0.5);
    resonz2 = Resonz.ar(feedbackSig, resonzFreq2 * (1 + LFNoise1.kr(resonzSweepSpeed).range(-resonzSweepRange, resonzSweepRange)), 0.5);
    resonzMix = (resonz1 + resonz2) * 0.5;

    // Sidechain ducking envelope triggered by percussion hits (simulated here as Impulse)
    sidechainEnv = EnvGen.kr(Env.perc(0.001, duckTime, amp: (10 ** (duckAmountDb / 20))), Impulse.kr(2), doneAction: 0);

    // Percussion: filtered white noise clicks with ring modulation
    percussionEnv = EnvGen.kr(Env.perc(clickAttack, clickDecay), Impulse.kr(2), doneAction: 0);
    percussionVelocity = LFNoise1.kr(0.5).range(0.22, 0.47); // velocity variation approx 28-42 scaled
    percussionClick = HPF.ar(WhiteNoise.ar(0.5), clickHpfFreq, clickHpfQ) * percussionEnv * percussionVelocity;
    percussionRingMod = SinOsc.ar(ringModFreq) * percussionEnv * LFNoise1.kr(0.5).range(ringDepthMin, ringDepthMax);
    percussionSig = percussionClick + percussionRingMod;

    // Echo effect chain - uses recipeDurationArg
    echoDelayTime = LFNoise1.kr(0.07).range(echoDelayMin, echoDelayMax);
    echoDelay = DelayC.ar(resonzMix + percussionSig, 1.0, echoDelayTime, echoFeedback);
    echoHpf = HPF.ar(echoDelay, echoHpfFreq);
    echoWet = Line.kr(echoWetMin, echoWetMax, recipeDurationArg); // Use arg here
    echoMix = XFade2.ar(resonzMix + percussionSig, echoHpf, echoWet);

    // Jitter injection
    jitterPhase = LFNoise1.kr(jitterFreq).range(-jitterAmount, jitterAmount);
    jitterDelayTime = delayTime + jitterPhase; // This variable is defined but not used in subsequent original logic.

    // Percussion dropout every ~7 seconds
    dropoutGate = Duty.kr(1 / dropoutInterval, 0, 1);
    percussionSig = percussionSig * dropoutGate;

    // Mix final signal
    sig = (bassOsc + wavefolder + feedbackSig + resonzMix + percussionSig + echoMix) * sidechainEnv;

    // Mono sum
    sig = sig.sum * 0.5;

    // Apply tanh for output level control
    finalSig = sig.tanh;

    Out.ar(out, finalSig ! 2);
  }).add;
