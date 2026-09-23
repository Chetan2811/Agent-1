"""Backward-compatible imports for the refactored trusted tool package."""

from tools.video_tools import *  # noqa: F403


def speed_up(input_path, output_path, factor):
    return change_speed(input_path, output_path, factor)  # noqa: F405
