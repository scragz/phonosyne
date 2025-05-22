(
"OSC_BOOTSTRAP: Script started.".postln;
NetAddr.langPort = 57120; // Ensure sclang listens on the correct port
"OSC_BOOTSTRAP: NetAddr.langPort set to 57120.".postln;

OSCdef.new(\loadScript, { |msg|
var scriptString = msg[1];
"OSC_BOOTSTRAP: /phonosyne/loadScript - Received script string (length: %):".format(scriptString.size).postln;
// "OSC_BOOTSTRAP: Script content: %".format(scriptString).postln; // Uncomment for deep debug
try {
scriptString.interpret;
"OSC_BOOTSTRAP: /phonosyne/loadScript - Script interpretation attempted.".postln;
// The interpreted script should define its own ready signals or OSCdefs if needed.
// For now, we assume it sets up /phonosyne/render and /phonosyne/stop
} { |error|
"OSC_BOOTSTRAP: /phonosyne/loadScript - ERROR interpreting script:".errorln;
error.reportError; // Post detailed error
};
}, '/phonosyne/loadScript');
"OSC_BOOTSTRAP: OSCdef for /phonosyne/loadScript defined.".postln;

// Signal that the bootstrap script is ready to receive further OSC commands (like loadScript)
"Phonosyne SuperCollider script ready".postln;
"OSC_BOOTSTRAP: Bootstrap ready signal posted.".postln;
)
