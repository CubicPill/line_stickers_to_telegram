import datetime
import math
import os
import shutil
import subprocess
from queue import Queue, Empty
from threading import Thread

import ffmpeg


class KakaoWebpProcessor(Thread):
    def __init__(self, temp_dir, task_queue):
        Thread.__init__(self)
        self.task_queue: Queue = task_queue
        self.temp_dir = temp_dir
        self.magick_bin = self.locate_magick_bin()

    def locate_magick_bin(self):
        return shutil.which('magick')

    def run(self) -> None:

        # first, use imagemagick to split frames
        # magick.exe .\4412296.emot_003.webp frames.png
        # use PIL to convert, ensure it's proper transparent png
        # then get frame duration, geometry, blending method
        # magick identify -format "(%T,%g,%[webp:mux-blend])|" .\4412296.emot_003.webp
        # finally use ffmpeg to convert to webm
        # ffmpeg -f concat -i .\list.txt  out.webm
        # and it can then be fed into regular processor

        while not self.task_queue.empty():
            try:
                uid, in_file, out_file = self.task_queue.get_nowait()
            except Empty:
                continue
            try:
                interim_file_path = os.path.join(self.temp_dir, f'conv_{uid}.webm')
                durations = self.to_webm(uid, in_file, interim_file_path)
                self.check_and_adjust_duration(uid, durations, interim_file_path, out_file)
            finally:
                self.task_queue.task_done()

    def make_frame_temp_dir(self, uid):
        frame_working_dir_path = os.path.join(self.temp_dir, 'frames_' + uid)
        if not os.path.isdir(frame_working_dir_path):
            os.mkdir(frame_working_dir_path)
        return frame_working_dir_path

    def make_frame_file(self, durations, frame_working_dir_path):
        with open(os.path.join(frame_working_dir_path, 'frames.txt'), 'w') as f:
            for i, d in enumerate(durations):
                f.write(f"file 'frame-{i}.png'\n")
                f.write(f'duration {d}\n')
        return os.path.join(frame_working_dir_path, 'frames.txt')

    def scale_and_concat_frame(self, frame_file_path, out_file, framerate):
        # framerate is needed here since telegram ios client will use framerate as play speed
        # ffmpeg will use 25 by default, making it playing too fast
        # https://bugs.telegram.org/c/14778
        ffmpeg.input(frame_file_path, format='concat') \
            .filter('scale', w='if(gt(iw,ih),512,-1)', h='if(gt(iw,ih),-1,512)') \
            .output(out_file, r=framerate) \
            .overwrite_output() \
            .run(quiet=True)

    def to_webm(self, uid, in_file, out_file):
        # TODO: Correctly handle blending and disposal (Animated WebP and maybe APNG)
        # TODO: check video length shrinking
        frame_working_dir_path = self.make_frame_temp_dir(uid)
        if not os.path.isdir(frame_working_dir_path):
            os.mkdir(frame_working_dir_path)
        subprocess.call([self.magick_bin, in_file, os.path.join(frame_working_dir_path, 'frame-%d.png')], shell=False)

        p = subprocess.Popen([self.magick_bin, 'identify', '-format', r'%T,%W,%H,%X,%Y,%[webp:mux-blend]|', in_file],
                             stdin=None, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, shell=False)
        out, err = p.communicate()
        frame_data_str_output = out.decode().strip()[:-1]

        frame_data = list()
        for fd in frame_data_str_output.split('|'):
            duration, w, h, x, y, blend_method = fd.split(',')
            duration = round(int(duration) / 100.0, 2)
            w, h, x, y = [int(x) for x in [w, h, x, y]]
            frame_data.append((duration, (w, h, x, y), blend_method))

        durations = [f[0] for f in frame_data]

        frame_file_path = self.make_frame_file(durations, frame_working_dir_path)
        avg_framerate = math.ceil((len(durations) + 1) / sum(durations))
        self.scale_and_concat_frame(frame_file_path, out_file, avg_framerate)

        return durations

    def check_and_adjust_duration(self, uid, durations, in_file, out_file):

        # probe, ensure it's max 3 seconds
        duration_str = ffmpeg.probe(in_file)['streams'][0]['tags']['DURATION']

        hms, us = duration_str.split('.')
        us = us[:6]
        duration_str = f'{hms}.{us}'
        duration_dt = datetime.datetime.strptime(duration_str, '%H:%M:%S.%f')
        duration_seconds = datetime.timedelta(seconds=duration_dt.second,
                                              microseconds=duration_dt.microsecond).total_seconds()

        if duration_seconds > 3:
            # print('Speedup needed', uid)
            # need to speedup
            total_duration_sum = sum(durations)
            # print(f'Detected:{duration_seconds}s, calculated:{total_duration_sum}s')

            factor = total_duration_sum / 3.0
            new_durations = [int(d / factor * 1000) / 1000 for d in durations]
            new_avg_framerate = math.ceil((len(new_durations) + 1) / sum(new_durations))

            frame_working_dir_path = self.make_frame_temp_dir(uid)
            frame_file_path = self.make_frame_file(new_durations, frame_working_dir_path)
            self.scale_and_concat_frame(frame_file_path, out_file, new_avg_framerate)
        else:
            shutil.copyfile(in_file, out_file)
            # just copy
