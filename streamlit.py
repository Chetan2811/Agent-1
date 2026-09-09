from pathlib import Path
import json
import mimetypes
import os

import streamlit as st

from plan_executor import PlanValidationError, execute_plan, validate_plan


PROJECT_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = PROJECT_DIR / "uploads"
OUTPUT_FOLDER = PROJECT_DIR / "output"
VIDEO_TYPES = ["mp4", "mov", "avi", "mkv", "webm", "m4v", "wmv"]
GEMINI_MODEL = "gemini-3.6-flash"

GEMINI_SYSTEM_PROMPT = """
You are a video-editing planner. Return only valid JSON, with no Markdown
code fences and no explanation. Never return FFmpeg commands or shell commands.

The only supported action right now is trim. The JSON schema is:
{"actions":[{"type":"trim","start":20,"end":30}]}

Rules:
- The top-level value must be an object containing an "actions" array.
- Use exactly one trim action.
- "start" and "end" are timestamps in seconds and must be numbers.
- "end" must be greater than "start".
- Extract the timestamps from the user's request.
- If the request does not specify a clear trim range, return:
  {"actions":[]}
""".strip()


def save_uploaded_video(uploaded_file) -> Path:
    UPLOAD_FOLDER.mkdir(exist_ok=True)
    input_path = UPLOAD_FOLDER / Path(uploaded_file.name).name
    with input_path.open("wb") as file:
        file.write(uploaded_file.getbuffer())
    return input_path


def get_output_path(input_path: Path) -> Path:
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    return OUTPUT_FOLDER / f"{input_path.stem}_processed.mp4"


def get_gemini_api_key() -> str | None:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if api_key:
        return api_key

    try:
        return st.secrets.get("GEMINI_API_KEY") or st.secrets.get("GOOGLE_API_KEY")
    except FileNotFoundError:
        return None


def generate_edit_plan(user_prompt: str, input_path: Path) -> dict:
    if not user_prompt.strip():
        raise ValueError("Enter a video-editing prompt first.")

    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError(
            "Gemini API key not found. Set GEMINI_API_KEY in your environment "
            "or Streamlit secrets."
        )

    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise RuntimeError(
            "The Gemini SDK is not installed. Run: pip install -U google-genai"
        ) from error

    request = (
        f"{GEMINI_SYSTEM_PROMPT}\n\n"
        f"Input video name for context: {input_path.name}\n"
        f"User editing request:\n{user_prompt.strip()}"
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=request,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0,
            ),
        )
    except Exception as error:
        raise RuntimeError(f"Gemini could not generate an edit plan: {error}") from error

    response_text = (response.text or "").strip()
    if not response_text:
        raise PlanValidationError("Gemini returned an empty edit plan.")

    try:
        plan = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise PlanValidationError(
            "Gemini returned malformed JSON. Please try a clearer editing request."
        ) from error

    return validate_plan(plan)


def show_download_button(processed_path: Path) -> None:
    mime_type = mimetypes.guess_type(processed_path.name)[0] or "video/mp4"
    with processed_path.open("rb") as file:
        st.download_button(
            label="Download Processed Video",
            data=file,
            file_name=processed_path.name,
            mime=mime_type,
        )


st.title("Valorant Montage Maker")
uploaded_file = st.file_uploader("Upload a video", type=VIDEO_TYPES)
video_prompt = st.text_area(
    "Describe the video edit you want",
    placeholder="Example: Cut from 20 to 30 seconds.",
    height=140,
)

if uploaded_file is None:
    st.info("Upload a video before generating an edit plan.")
else:
    if st.session_state.get("uploaded_file_name") != uploaded_file.name:
        input_path = save_uploaded_video(uploaded_file)
        st.session_state["uploaded_file_name"] = uploaded_file.name
        st.session_state["input_file_path"] = str(input_path)
        st.session_state["output_file_path"] = str(get_output_path(input_path))
        st.session_state.pop("edit_plan", None)
        st.session_state.pop("processed_video_path", None)
        st.session_state.pop("ffmpeg_output", None)

    st.success(f"Uploaded: {uploaded_file.name}")

    if st.button("Generate Edit Plan", type="primary"):
        input_path = Path(st.session_state["input_file_path"])
        try:
            plan = generate_edit_plan(video_prompt, input_path)
        except (PlanValidationError, RuntimeError, ValueError) as error:
            st.session_state.pop("edit_plan", None)
            st.error(str(error))
        else:
            st.session_state["edit_plan"] = plan
            st.session_state.pop("processed_video_path", None)
            st.success("Edit plan generated.")

    if st.session_state.get("edit_plan"):
        st.subheader("Generated Edit Plan")
        st.json(st.session_state["edit_plan"])

        if st.button("Run Edit"):
            input_path = Path(st.session_state["input_file_path"])
            output_path = Path(st.session_state["output_file_path"])
            try:
                with st.spinner("Processing video..."):
                    execute_plan(st.session_state["edit_plan"], input_path, output_path)
            except (PlanValidationError, RuntimeError, ValueError) as error:
                st.error(str(error))
            else:
                st.session_state["processed_video_path"] = str(output_path)
                st.success(f"Processed video saved to: {output_path}")

processed_video_path = st.session_state.get("processed_video_path")
if processed_video_path:
    processed_path = Path(processed_video_path)
    if processed_path.exists():
        show_download_button(processed_path)
    else:
        st.warning("Processed video is no longer available in the output folder.")
