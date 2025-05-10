# Phonosyne

Phonosyne is a multi-agent AI system designed to transform natural-language sound design briefs into collections of unique, validated audio samples. It leverages a pipeline of specialized LLM-powered agents (Designer, Analyzer, Compiler) to plan, detail, and generate DSP code, which is then executed to produce `.wav` files.

The project aims to provide both a command-line tool (`phonosyne`) and a Python SDK for generating sound libraries based on textual prompts, automating a complex creative and technical process.

## Key Features

- **AI-Powered Sound Design**: Converts text prompts into structured sound design plans and ultimately into audio.
- **Multi-Agent Pipeline**: Uses a sequence of specialized agents for planning, synthesis recipe generation, and code compilation.
- **Sandboxed Code Execution**: Executes LLM-generated Python DSP code in a controlled environment using `smolagents.LocalPythonExecutor`.
- **Audio Validation**: Ensures generated samples meet technical specifications (sample rate, duration, bit depth, peak levels).
- **Concurrency**: Supports parallel processing of samples to speed up generation.
- **Extensible**: Designed with a modular architecture for future enhancements.

## Getting Started

(TODO: Add installation and basic usage instructions here once the project is more mature.)

## Project Status

This project is currently under active development (Alpha).
