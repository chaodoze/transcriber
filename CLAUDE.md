# Podcast Transcriber MCP Server

## Project Overview
MCP server for podcast transcription with speaker diarization, optimized for Apple Silicon.

## Tech Stack
- **Transcription**: mlx-whisper (distil-whisper-large-v3) - native Apple Silicon
- **Diarization**: pyannote-audio (speaker-diarization-3.1)
- **MCP Framework**: FastMCP
- **Audio Loading**: torchaudio (workaround for torchcodec issues)

## Key Learnings

### pyannote-audio API
- Use `token=` parameter, not `use_auth_token=` (deprecated)
- When passing waveform dict to pipeline, output may be `DiarizeOutput` instead of `Annotation`
- Handle both: check for `itertracks()` method or `speaker_diarization` attribute
- Requires HuggingFace token and model license acceptance

### Audio Loading
- torchcodec has FFmpeg compatibility issues on macOS
- Workaround: pre-load audio with `torchaudio.load()` and pass as dict:
  ```python
  waveform, sample_rate = torchaudio.load(audio_path)
  audio_input = {"waveform": waveform, "sample_rate": sample_rate}
  pipeline(audio_input)
  ```

### Speaker Name Detection
- Pattern matching prone to false positives ("all", "going" from "I'm going...")
- Use strict patterns with minimum length (3+ chars)
- Filter against common word list
- Best patterns: "my name is [Name]", "this is [Name]"

## Environment Variables
- `HF_TOKEN`: HuggingFace token for pyannote models (required)
- `WHISPER_MODEL`: Override default model (optional)

## Running the Server
```bash
source .venv/bin/activate
export HF_TOKEN="your_token_here"
python -m src.transcriber.server
```

## Performance (64-min podcast, M-series Mac)
- Transcription: ~8.5 minutes
- Diarization: ~10 minutes
- Total: ~20 minutes for full pipeline
