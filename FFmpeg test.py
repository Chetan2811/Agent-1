import ffmpeg

stream = ffmpeg.input('uploads/split2.mp4')
stream = ffmpeg.trim(stream, start=0, end=10)
stream = ffmpeg.filter(stream, 'fps', fps=30)
stream = ffmpeg.output(stream, 'output/output_%04d.gif')

ffmpeg.run(stream)