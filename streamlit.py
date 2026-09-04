from pathlib import Path
import mimetypes
import shlex
import subprocess

import streamlit as st


PROJECT_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = PROJECT_DIR / "uploads"
OUTPUT_FOLDER = PROJECT_DIR / "output"
VIDEO_TYPES = ["mp4", "mov", "avi", "mkv", "webm", "m4v", "wmv"]

DEFAULT_FFMPEG_COMMAND = (
    "ffmpeg -y -ss 00:00:20 -i {input} "
    "-t 10 "
    "-c copy "
    "{output}"
)

def save_uploaded_video(uploaded_file) -> Path:
    UPLOAD_FOLDER.mkdir(exist_ok=True)
    input_path = UPLOAD_FOLDER / Path(uploaded_file.name).name

    with input_path.open("wb") as file:
        file.write(uploaded_file.getbuffer())

    return input_path


def get_output_path(input_path: Path) -> Path:
    OUTPUT_FOLDER.mkdir(exist_ok=True)
    return OUTPUT_FOLDER / f"{input_path.stem}_processed.mp4"


def build_ffmpeg_command(command_template: str, input_path: Path, output_path: Path):
    if "{input}" not in command_template or "{output}" not in command_template:
        raise ValueError("The FFmpeg command must include {input} and {output}.")

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

ffmpeg_prompt = st.text_area(
    "FFmpeg command",
    value=DEFAULT_FFMPEG_COMMAND,
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

    if st.button("Run FFmpeg", type="primary"):
        input_path = save_uploaded_video(uploaded_file)
        output_path = get_output_path(input_path)

        try:
            command_text, command_parts = build_ffmpeg_command(
                ffmpeg_prompt,
                input_path,
                output_path,
            )
        except ValueError as error:
            st.error(str(error))
        else:
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
