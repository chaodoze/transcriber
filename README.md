# Reader MCP

An MCP (Model Context Protocol) server for podcast transcription with speaker diarization, optimized for Apple Silicon.

## Features

- **Fast transcription** using mlx-whisper (Apple Silicon optimized)
- **Speaker diarization** using pyannote-audio
- **Filler word removal** (um, uh, like, you know, etc.)
- **Speaker name identification** from context
- **Multiple export formats** (TXT, SRT, VTT)

## Installation

```bash
# Clone the repository
git clone https://github.com/your-username/transcriber.git
cd transcriber

# Install dependencies
uv sync

# Set up environment
cp .env.example .env
# Edit .env with your HuggingFace token
```

## Configuration

You need a HuggingFace token for the pyannote diarization models:

1. Create account at https://huggingface.co
2. Accept terms at https://huggingface.co/pyannote/speaker-diarization-3.1
3. Create token at https://huggingface.co/settings/tokens
4. Add to `.env`: `HF_TOKEN=your_token_here`

## Usage

### With Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "transcriber": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/transcriber", "transcriber"],
      "env": {
        "HF_TOKEN": "your_hf_token_here"
      }
    }
  }
}
```

### With Claude Code

```bash
claude mcp add transcriber -- uv run --directory /path/to/transcriber transcriber
```

## Tools

### transcribe_podcast

Full transcription with speaker diarization.

```
transcribe_podcast(
    audio_path: str,      # Path to audio file
    language: str = "en", # Language code
    remove_fillers: bool = True,
    identify_speakers: bool = True
)
```

### transcribe_quick

Fast transcription without diarization.

### export_transcript

Export to TXT, SRT, or VTT format.

## License

MIT
