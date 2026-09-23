# Valorant Montage Maker

Valorant Montage Maker is an AI-assisted video editing tool that creates highlight montages
from gameplay videos. It uses Gemini to detect key moments such as kills, headshots, and
clutches, then generates a montage from natural-language instructions. Trusted FFmpeg tools
render the final video.

## Features

- **AI-powered video analysis:** Detects kills, headshots, multi-kills, and other gameplay
  events with the Gemini API.
- **Customizable montages:** Accepts plain-English requests such as "Highlight my kills with
  slow-motion headshots and transitions."
- **FFmpeg video editing:** Trims clips, adds transitions, adjusts speed, and mixes background
  music.
- **User-friendly interface:** Provides a Streamlit UI for uploads, previews, and downloads.
- **Optional FastAPI backend:** Exposes REST endpoints for programmatic access.
- **Secure and reliable execution:** Validates model output before running deterministic editing
  tools.

## How It Works

1. **Upload videos:** Add one or more Valorant gameplay videos.
2. **Describe your montage:** Enter a natural-language request, such as "Highlight kills with
   three seconds before and after each event."
3. **Analyze gameplay:** Gemini analyzes the videos and identifies gameplay events.
4. **Generate an edit plan:** The application validates an AI-generated sequence of editing
   actions.
5. **Render the montage:** FFmpeg applies cuts, effects, transitions, and optional background
   music.
6. **Download the result:** Preview and download the completed montage.

## Project Structure

```text
app.py          # Streamlit UI
api.py          # FastAPI backend
ai/             # Gemini analyzer and planner
schemas/        # Pydantic validation models
services/       # Core orchestration, persistence, and storage
tools/          # FFmpeg-based video and audio tools
cv/             # OpenCV video metadata utilities
evaluation/     # AI event-detection evaluation tools
tests/          # Unit and synthetic-media tests
Dockerfile      # Container configuration
```

## Local Setup

### Prerequisites

- Python 3.11 or newer
- FFmpeg installed and available on `PATH`

### Installation

From the repository root, create a virtual environment and install the dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy the example environment file and add your Gemini API key:

```bash
cp .env.example .env
```

The primary Gemini settings are:

```dotenv
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-3.6-flash
```

Start the Streamlit application:

```bash
streamlit run app.py
```

## Docker Setup

Build the image:

```bash
docker build -t valorant-montage-maker .
```

Run the container:

```bash
docker run --rm -p 8501:8501 --env-file .env valorant-montage-maker
```

## Testing

Run linting and the test suite:

```bash
ruff check .
python -m pytest
```

## Key Technologies

- **Python:** Core application language
- **Streamlit:** Video upload, preview, and download interface
- **FastAPI:** Optional REST API
- **FFmpeg:** Video and audio processing
- **OpenCV:** Video metadata extraction
- **Gemini API:** Gameplay analysis and edit planning
- **Pydantic:** Schema validation and enforcement
- **SQLite:** Local job metadata storage

## Limitations

- **AI dependency:** Detection quality depends on Gemini and the quality of the uploaded video.
- **Synchronous processing:** Analysis and rendering may take time for large videos.
- **Local storage:** The current implementation uses local files and SQLite rather than cloud
  storage or a managed database.

## Future Improvements

- Train a local kill-feed detector to reduce reliance on Gemini.
- Add a worker queue for large processing jobs.
- Introduce a timeline editor for manual adjustments.
- Add optional cloud storage and managed database integrations.
