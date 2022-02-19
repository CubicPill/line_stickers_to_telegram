import datetime
import os
import shutil
import subprocess
import traceback
from queue import Queue, Empty
from threading import Thread

import ffmpeg
from PIL import Image


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
        # use PIL to convert, ensure it's proper transparent png
        # then get frame duration, geometry, blending method, disposal method
        # finally use ffmpeg to convert to webm
        # then it can then be fed into regular processor

        while not self.task_queue.empty():
            try:
                uid, in_file, out_file = self.task_queue.get_nowait()
            except Empty:
                continue
            try:
                interim_file_path = os.path.join(self.temp_dir, f'conv_{uid}.webm')
                durations = self.to_webm(uid, in_file, interim_file_path)
                self.check_and_adjust_duration(uid, durations, interim_file_path, out_file)
            except Exception as e:
                print(f'Exception while processing: {uid}, {in_file}:', e)
                traceback.print_exc()
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
            # last frame need to be put twice, see: https://trac.ffmpeg.org/wiki/Slideshow
            f.write(f"file 'frame-{len(durations) - 1}.png'\n")
        return os.path.join(frame_working_dir_path, 'frames.txt')

    def scale_and_concat_frame(self, frame_file_path, out_file):
        # framerate is needed here since telegram ios client will use framerate as play speed
        # in fact, framerate in webm should be informative only
        # ffmpeg will use 25 by default
        # so we set vsync=1 (cfr), let ffmpeg duplicate some frames to make ios happy
        # this will cause file size to increase a bit, but it should be OK
        # also 1/framerate seems to be the minimum unit of ffmpeg to encode frame duration
        # so shouldn't set it too small - which will cause too much error
        # https://bugs.telegram.org/c/14778

        framerate = 25
        ffmpeg.input(frame_file_path, format='concat') \
            .filter('scale', w='if(gt(iw,ih),512,-1)', h='if(gt(iw,ih),-1,512)') \
            .output(out_file, r=framerate, vsync=1) \
            .overwrite_output() \
            .run(quiet=True)

    def split_webp_frames(self, in_file, frame_working_dir_path):
        # split frames using imagemagick, and reconstruct frames based on disposal/blending
        if not os.path.isdir(frame_working_dir_path):
            os.mkdir(frame_working_dir_path)
        subprocess.call([self.magick_bin, in_file, os.path.join(frame_working_dir_path, 'frame-%d.png')], shell=False)

        p = subprocess.Popen(
            [self.magick_bin, 'identify', '-format', r'%T,%W,%H,%w,%h,%X,%Y,%[webp:mux-blend],%D|', in_file],
            stdin=None, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=False)
        out, err = p.communicate()
        frame_data_str_output = out.decode().strip()[:-1]
        image_w, image_h = 0, 0
        frame_data = list()
        for fd in frame_data_str_output.split('|'):
            duration, cw, ch, w, h, x, y, blend_method, dispose_method = fd.split(',')
            duration = round(int(duration) / 100.0, 2)
            cw, ch, w, h, x, y = [int(i) for i in [cw, ch, w, h, x, y]]
            image_w, image_h = cw, ch
            frame_data.append((duration, (w, h, x, y), blend_method, dispose_method))

        # added for debugging purposes
        try:
            os.mkdir(os.path.join(frame_working_dir_path, 'raw'))
        except:
            pass
        for i in os.listdir(frame_working_dir_path):
            if i.startswith('frame-') and i.endswith('.png'):
                shutil.copy(os.path.join(frame_working_dir_path, i), os.path.join(frame_working_dir_path, 'raw'))

        self.process_blend_and_dispose(frame_data, frame_working_dir_path, image_h, image_w)

        durations = [f[0] for f in frame_data]
        return durations

    def process_blend_and_dispose(self, frame_data, frame_working_dir_path, image_h, image_w):
        # background color should be transparent
        canvas = Image.new('RGBA', (image_w, image_h), (255, 255, 255, 0))
        for i, d in enumerate(frame_data):
            # since dispose_method applies to after displaying current frame,
            # for this frame we need data from last frame
            duration, (w, h, x, y), blend_method, _ = d
            if i == 0:
                dispose_method = 'None'
                _w, _h, _x, _y = 0, 0, 0, 0  # make linter happy
            else:
                _, (_w, _h, _x, _y), _, dispose_method = frame_data[i - 1]

            frame_file = os.path.join(frame_working_dir_path, f'frame-{i}.png')
            frame_image = Image.open(frame_file).convert('RGBA')

            if dispose_method == 'Background':
                # last frame to be disposed to background color (transparent)
                rect = Image.new('RGBA', (_w, _h), (255, 255, 255, 0))
                canvas.paste(rect, (_x, _y, _w + _x, _h + _y))

            # else do not dispose, do nothing
            if blend_method == 'AtopPreviousAlphaBlend':  # do not blend
                canvas.paste(frame_image, (x, y, w + x, h + y))
            else:  # alpha blending
                try:
                    canvas.paste(frame_image, (x, y, w + x, h + y), frame_image)
                except Exception as e:
                    print(frame_file, e)
                    raise Exception

            canvas.save(os.path.join(frame_working_dir_path, f'frame-{i}.png'))

    def to_webm(self, uid, in_file, out_file):

        frame_working_dir_path = self.make_frame_temp_dir(uid)
        durations = self.split_webp_frames(in_file, frame_working_dir_path)

        frame_file_path = self.make_frame_file(durations, frame_working_dir_path)
        # avg_framerate = round((len(durations) + 2) / sum(durations), 3)
        self.scale_and_concat_frame(frame_file_path, out_file)

        return durations

    def probe_duration(self, file):
        duration_str = ffmpeg.probe(file)['streams'][0]['tags']['DURATION']

        hms, us = duration_str.split('.')
        us = us[:6]
        duration_str = f'{hms}.{us}'
        duration_dt = datetime.datetime.strptime(duration_str, '%H:%M:%S.%f')
        duration_seconds = datetime.timedelta(seconds=duration_dt.second,
                                              microseconds=duration_dt.microsecond).total_seconds()
        return duration_seconds

    def check_and_adjust_duration(self, uid, durations, in_file, out_file):

        # probe, ensure it's max 3 seconds
        duration_seconds = self.probe_duration(in_file)

        if duration_seconds > 3:
            factor = duration_seconds / 3.0
            while True:
                new_durations = [int(d / factor * 1000) / 1000 for d in durations]
                # new_avg_framerate = math.ceil((len(new_durations) + 2) / sum(new_durations) * 1000) / 1000
                frame_working_dir_path = self.make_frame_temp_dir(uid)
                frame_file_path = self.make_frame_file(new_durations, frame_working_dir_path)
                self.scale_and_concat_frame(frame_file_path, out_file)
                new_duration_seconds = self.probe_duration(file=out_file)
                if new_duration_seconds > 3:
                    factor = factor * 1.05
                else:
                    break
        else:  # just copy
            shutil.copyfile(in_file, out_file)
