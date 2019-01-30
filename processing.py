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

    def remove_alpha_geq(self, in_stream):
        """
        use geq filter to remove alpha
        just calculate the new color for each pixel on a white background
        slower than overlay method
        cannot handle pal8
        :param in_stream:
        :return:
        """
        return in_stream \
            .filter('geq',
                    r='(r(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                    g='(g(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                    b='(b(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                    a=255)

    def remove_alpha_overlay(self, in_stream):
        """
        overlay image on a white background
        faster than geq filter
        cannot handle ya8
        :param in_stream:
        :return:
        """
        return in_stream \
            .filter('pad', w='iw*2', h='ih', x='iw', y='ih', color='white') \
            .crop(width='iw/2', height='ih', x=0, y=0) \
            .overlay(in_stream)

    def remove_alpha(self, in_stream, pix_fmt):
        if pix_fmt == 'ya8':  # use geq method
            return self.remove_alpha_geq(in_stream)
        else:
            return self.remove_alpha_overlay(in_stream)

    def to_gif(self, in_file, out_file):
        pix_fmt = ffmpeg.probe(in_file)['streams'][0]['pix_fmt']
        input_stream = ffmpeg.input(in_file, f='apng')
        in1 = self.remove_alpha(input_stream, pix_fmt)

        in2 = input_stream.filter('palettegen')
        ffmpeg.filter([in1, in2], 'paletteuse') \
            .output(out_file) \
            .overwrite_output() \
            .run(quiet=True)

    def to_video(self, in_pic, in_audio, out_file):
        streams = list()
        pix_fmt = ffmpeg.probe(in_pic)['streams'][0]['pix_fmt']
        in_pic_stream = ffmpeg.input(in_pic, f='apng')
        video_output = self.remove_alpha(in_pic_stream, pix_fmt) \
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
