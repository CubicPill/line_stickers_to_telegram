from enum import Enum
from threading import Thread

import ffmpeg


class ProcessOption(Enum):
    NONE = 'none'
    SCALE = 'scale'
    TO_GIF = 'to_gif'
    TO_VIDEO = 'to_video'


class ImageProcessorThread(Thread):
    def __init__(self, queue, option: ProcessOption, temp_dir):
        Thread.__init__(self, name='ImageProcessorThread')
        self.queue = queue
        self.option = option
        self.temp_dir = temp_dir

    def run(self):
        if self.option == ProcessOption.NONE:
            # this should not happen, bro. Why are you creating this thread?
            return
        while not self.queue.empty():
            try:
                if self.option == ProcessOption.TO_VIDEO:
                    in_pic, in_audio, out_file = self.queue.get_nowait()
                    self.to_video(in_pic, in_audio, out_file)
                else:

                    in_file, out_file = self.queue.get_nowait()
                    if self.option == ProcessOption.SCALE:
                        self.scale_image(in_file, out_file)
                    elif self.option == ProcessOption.TO_GIF:
                        self.to_gif(in_file, out_file)
                    else:
                        # shouldn't get there
                        pass
            finally:
                self.queue.task_done()

    def scale_image(self, in_file, out_file):
        ffmpeg.input(in_file).filter('scale', w='if(gt(iw,ih),512,-1)', h='if(gt(iw,ih),-1,512)').output(out_file)

    def to_gif(self, in_file, out_file):
        input_stream = ffmpeg.input(in_file, f='apng')
        # overlay transparent png on white background
        in1 = input_stream.filter('geq',
                                  r='(r(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                                  g='(g(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                                  b='(b(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                                  a=255)

        in2 = input_stream.filter('palettegen')
        ffmpeg.filter([in1, in2], 'paletteuse') \
            .output(out_file) \
            .overwrite_output() \
            .run(quiet=True)

    def to_video(self, in_pic, in_audio, out_file):
        streams = list()
        video_output = ffmpeg.input(in_pic, f='apng') \
            .filter('geq',  # overlay transparent png on white background
                    r='(r(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                    g='(g(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                    b='(b(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                    a=255
                    ) \
            .filter('scale',
                    w='trunc(iw/2)*2',
                    h='trunc(ih/2)*2'  # enable H.264
                    )

        streams.append(video_output)
        if in_audio:
            audio_input = ffmpeg.input(in_audio)
            streams.append(audio_input)
        ffmpeg.output(*streams, out_file, pix_fmt='yuv420p', movflags='faststart') \
            .overwrite_output().run(quiet=True)
