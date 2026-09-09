# Valorant Montage Maker

The app uses Gemini as a video-editing planner. Gemini returns a JSON edit
plan; Python validates that plan and executes predefined tools in
`video_tools.py`. Gemini never generates or executes shell commands.

Install dependencies:

```bash
pip install -r requirements.txt
```

Set a Gemini API key and start Streamlit:

```bash
export GEMINI_API_KEY="your-api-key"
streamlit run streamlit.py
```

Current workflow:

1. Upload a video.
2. Enter a prompt such as `Cut from 20 to 30 seconds`.
3. Click **Generate Edit Plan** to create and display the JSON plan.
4. Click **Run Edit** to execute the validated plan with FFmpeg.
5. Download the processed MP4 from the app.

The first version supports one `trim` action. New actions should be added as
predefined functions in `video_tools.py` and explicitly registered in
`plan_executor.py`.
