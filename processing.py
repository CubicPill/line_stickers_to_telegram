import os
import subprocess
from enum import Enum
from threading import Thread

import ffmpeg


class ProcessOption(Enum):
    NONE = 'none'
    SCALE = 'scale'
    TO_GIF = 'to_gif'
    TO_VIDEO = 'to_video'


class ImageProcessorThread(Thread):
    # TODO: conversion
    def __init__(self, queue, option: ProcessOption):
        Thread.__init__(self, name='ImageProcessorThread')
        self.queue = queue
        self.option = option

    def run(self):
        if self.option == ProcessOption.NONE:
            # this should not happen, bro. Why are you creating this thread?
            return
        while not self.queue.empty():
            if self.option == ProcessOption.TO_VIDEO:
                in_pic, in_audio, out_file = self.queue.get_nowait()
                to_video(in_pic, in_audio, out_file)
            else:

                in_file, out_file = self.queue.get_nowait()
                if self.option == ProcessOption.SCALE:
                    scale_image(in_file, out_file)
                elif self.option == ProcessOption.TO_GIF:
                    to_gif(in_file, out_file)
                else:
                    # shouldn't get there
                    pass


def scale_image(in_file, out_file):
    ffmpeg.input(in_file).filter('scale', w='if(gt(iw,ih),512,-1)', h='if(gt(iw,ih),-1,512)').output(out_file)


def to_gif(in_file, out_file):
    input_stream = ffmpeg.input(in_file, f='apng')
    temp_apng_filename = 'tmp' + os.path.sep + 'temp_' + in_file.split(os.path.sep)[-1]
    temp_palette_filename = 'tmp' + os.path.sep + 'temp_palette_' + in_file.split(os.path.sep)[-1]
    input_stream \
        .filter('pad', w='iw*2', h='ih', x='iw', y='ih', color='white') \
        .crop(width='iw/2', height='ih', x=0, y=0) \
        .overlay(input_stream) \
        .output(temp_apng_filename, f='apng', plays=0) \
        .overwrite_output() \
        .run()
    input_stream.filter('palettegen').output(temp_palette_filename) \
        .overwrite_output() \
        .run()
    ffmpeg.input(temp_apng_filename).output(out_file, f='gif') \
        .overwrite_output() \
        .run()
    # currently I have no idea how to do this in ffmpeg-python
    subprocess.Popen(
        ['ffmpeg', '-i', temp_apng_filename, '-i', temp_palette_filename, '-lavfi', 'paletteuse', '-y', out_file])


def to_video(in_pic, in_audio, out_file):
    input_stream = ffmpeg.input(in_pic, f='apng')
    if in_audio:
        pass
    input_stream \
        .filter('pad', w='iw*2', h='ih', x='iw', y='ih', color='white') \
        .crop(width='iw/2', height='ih', x=0, y=0) \
        .overlay(input_stream, format='rgb') \
        .output(out_file, f='mp4') \
        .overwrite_output() \
        .run()
