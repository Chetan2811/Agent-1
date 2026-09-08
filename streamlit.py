from pathlib import Path
import mimetypes
import os
import shlex
import subprocess

import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = PROJECT_DIR / "uploads"
OUTPUT_FOLDER = PROJECT_DIR / "output"
VIDEO_TYPES = ["mp4", "mov", "avi", "mkv", "webm", "m4v", "wmv"]

GEMINI_MODEL = "gemini-3.6-flash"

GEMINI_SYSTEM_PROMPT = """
You write exactly one safe FFmpeg command for a local video-processing app.

Rules:
- Return only the command. Do not use Markdown fences or explanations.
- The command must start with ffmpeg.
- Use {input} as the input video path and {output} as the output video path.
- Include -y so an existing output can be replaced.
- Produce a playable MP4 at {output}; use compatible H.264 video and AAC audio
  when re-encoding is needed.
- Do not use shell operators, pipes, redirects, multiple commands, filters that
  require external files, or any input/output path other than the placeholders.
- Never delete or overwrite the input file.
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


def generate_ffmpeg_command(user_prompt: str, input_path: Path) -> str:
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
    except ImportError as error:
        raise RuntimeError(
            "The Gemini SDK is not installed. Run: pip install -U google-genai"
        ) from error

    client = genai.Client(api_key=api_key)
    request = (
        f"{GEMINI_SYSTEM_PROMPT}\n\n"
        f"Input filename: {input_path.name}\n"
        f"User video-editing prompt:\n{user_prompt.strip()}"
    )
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=request,
        )
    except Exception as error:
        raise RuntimeError(f"Gemini could not generate an FFmpeg command: {error}") from error

    command = (response.text or "").strip()
    if command.startswith("```"):
        command = command.removeprefix("```").removesuffix("```").strip()
        if command.startswith("bash"):
            command = command[4:].lstrip()

    if not command:
        raise ValueError("Gemini returned an empty FFmpeg command.")

    return command


def build_ffmpeg_command(command_template: str, input_path: Path, output_path: Path):
    if "{input}" not in command_template or "{output}" not in command_template:
        raise ValueError("The FFmpeg command must include {input} and {output}.")

    if any(operator in command_template for operator in [";", "&&", "||", "|", ">", "<"]):
        raise ValueError("The generated command contains an unsupported shell operator.")

    command_text = command_template.replace("{input}", shlex.quote(str(input_path)))
    command_text = command_text.replace("{output}", shlex.quote(str(output_path)))
    command_parts = shlex.split(command_text)

    if not command_parts or Path(command_parts[0]).name != "ffmpeg":
        raise ValueError("The command must start with ffmpeg.")

    return command_text, command_parts


def show_download_button(processed_path: Path):
    mime_type = mimetypes.guess_type(processed_path.name)[0] or "application/octet-stream"

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
    placeholder="Example: Trim the first 10 seconds, resize to 1080p, and add a fade in and fade out.",
    height=140,
)

if uploaded_file is None:
    st.info("Upload a video before running FFmpeg.")
else:
    if st.session_state.get("uploaded_file_name") != uploaded_file.name:
        st.session_state["uploaded_file_name"] = uploaded_file.name
        st.session_state.pop("processed_video_path", None)
        st.session_state.pop("ffmpeg_command", None)
        st.session_state.pop("ffmpeg_output", None)

    st.success(f"Uploaded: {uploaded_file.name}")

    if st.button("Generate and Process Video", type="primary"):
        input_path = save_uploaded_video(uploaded_file)
        output_path = get_output_path(input_path)

        try:
            generated_command = generate_ffmpeg_command(video_prompt, input_path)
            command_text, command_parts = build_ffmpeg_command(
                generated_command,
                input_path,
                output_path,
            )
        except (RuntimeError, ValueError) as error:
            st.error(str(error))
        else:
            st.session_state["video_prompt"] = video_prompt
            st.code(command_text, language="bash")

            with st.spinner("Processing video..."):
                result = subprocess.run(
                    command_parts,
                    cwd=PROJECT_DIR,
                    capture_output=True,
                    text=True,
                )

            ffmpeg_output = "\n".join(
                output for output in [result.stdout, result.stderr] if output
            ).strip()

            st.session_state["ffmpeg_command"] = command_text
            st.session_state["ffmpeg_output"] = ffmpeg_output

            if result.returncode != 0:
                st.error("FFmpeg failed. Check the console output below.")
            elif not output_path.exists():
                st.error("FFmpeg finished, but the processed video was not found.")
            else:
                st.session_state["processed_video_path"] = str(output_path)
                st.success(f"Processed video saved to: {output_path}")

if st.session_state.get("ffmpeg_command"):
    if st.session_state.get("video_prompt"):
        st.subheader("Prompt Used")
        st.write(st.session_state["video_prompt"])
    st.subheader("Last FFmpeg Command")
    st.code(st.session_state["ffmpeg_command"], language="bash")

if st.session_state.get("ffmpeg_output"):
    st.subheader("FFmpeg Console Output")
    st.text_area(
        "Console output",
        value=st.session_state["ffmpeg_output"],
        height=220,
        disabled=True,
    )

processed_video_path = st.session_state.get("processed_video_path")
if processed_video_path:
    processed_path = Path(processed_video_path)

    if processed_path.exists():
        show_download_button(processed_path)
    else:
        st.warning("Processed video is no longer available in the output folder.")
        
