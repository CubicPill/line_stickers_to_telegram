import datetime
import os.path
import queue
import shutil
import subprocess
import traceback
from enum import Enum
from threading import Lock, Thread

import ffmpeg

from utils import StickerType, increase_counter, sticker_type_properties

GIF_ALPHA_THRESHOLD = 1
WEBM_SIZE_KB_MAX = 256
WEBM_DURATION_SEC_MAX = 3

_MAGICK_BIN = shutil.which('magick')
_print_lock = Lock()


class OutputFormat(Enum):
    # this will also be the file extension
    GIF = 'gif'
    WEBM = 'webm'
    MP4 = 'mp4'
    APNG = 'png'


class Operation(Enum):
    SCALE = 'scale'
    OVERLAY = 'overlay'
    REMOVE_ALPHA = 'remove_alpha'
    TO_GIF = 'to_gif'
    TO_WEBM = 'to_webm'
    TO_MP4 = 'to_mp4'


class ProcessTask:
    def __init__(self, sticker_id, in_img_path, in_audio_path, in_overlay_path, scale_px, operations,
                 result_output_path):
        self.sticker_id = sticker_id
        self.in_img = in_img_path
        self.in_audio = in_audio_path
        self.in_overlay = in_overlay_path
        self.scale_px = scale_px
        self.operations = operations
        self.result_path = result_output_path


class ImageProcessorThread(Thread):
    def __init__(self, queue, temp_dir, sticker_type: StickerType, output_format: OutputFormat):
        Thread.__init__(self, name='ImageProcessorThread')
        self.queue = queue
        self.temp_dir = temp_dir
        self.sticker_type = sticker_type
        self.output_format = output_format
        self._current_sticker_id = None
        (
            self._sticker_has_animation,
            self._sticker_has_sound,
            self._sticker_has_popup,
            self._sticker_has_text_overlay,
            self._sticker_is_emoji
        ) = sticker_type_properties(self.sticker_type)

    def run(self):
        while not self.queue.empty():
            try:
                task: ProcessTask = self.queue.get_nowait()
            except queue.Empty:
                continue
            self._current_sticker_id = str(task.sticker_id)
            try:
                curr_in = task.in_img
                for i, op in enumerate(task.operations):
                    curr_out = os.path.join(self.temp_dir, f'{self._current_sticker_id}_interim_{i}.tmp')
                    if op == Operation.SCALE:
                        self.scale_image(curr_in, curr_out, task.scale_px)
                    elif op == Operation.OVERLAY:
                        self.overlay_sticker_message(curr_in, task.in_overlay, curr_out)
                    elif op == Operation.REMOVE_ALPHA:
                        self.remove_alpha(curr_in, curr_out)
                    elif op == Operation.TO_GIF:
                        self.to_gif(curr_in, curr_out)
                    elif op == Operation.TO_WEBM:
                        frame_dir = self.make_frame_temp_dir()
                        self.split_apng_frames(curr_in, frame_dir)
                        durations = self.get_animation_delays(curr_in)
                        webm_uncapped = os.path.join(self.temp_dir, f'{self._current_sticker_id}.raw.webm')
                        self.to_webm(durations, frame_dir, webm_uncapped)
                        self.cap_webm_duration_and_size(durations, webm_uncapped, frame_dir, curr_out)
                    elif op == Operation.TO_MP4:
                        self.to_video(curr_in, task.in_audio, curr_out)
                    curr_in = curr_out
                shutil.copy(curr_in, task.result_path)
            except ffmpeg.Error as e:
                with _print_lock:
                    print('Error occurred while processing', e, task.sticker_id)
                    print('------stdout------')
                    print(e.stdout.decode())
                    print('------end------')
                    print('------stderr------')
                    print(e.stderr.decode())
                    print('------end------')
                    traceback.print_exc()
            finally:
                self.queue.task_done()
                increase_counter()

    def make_frame_temp_dir(self):
        frame_working_dir_path = os.path.join(self.temp_dir, 'frames_' + self._current_sticker_id)
        if not os.path.isdir(frame_working_dir_path):
            os.mkdir(frame_working_dir_path)
        return frame_working_dir_path

    def overlay_sticker_message(self, in_img, in_overlay, out_file):
        # overlay in_overlay on in_img
        subprocess.call([_MAGICK_BIN, in_img, in_overlay, '-gravity', 'center', '-composite', out_file])

    def scale_image(self, in_file, out_file, size):
        if self._sticker_has_animation:
            ffmpeg.input(in_file, f='apng').filter('scale', w=f'if(gt(iw,ih),{size},-1)',
                                                   h=f'if(gt(iw,ih),-1,{size})').output(
                    out_file, pix_fmt='rgba', f='apng').run(quiet=True)
        else:
            subprocess.call([_MAGICK_BIN, 'PNG:' + in_file, '-resize', f'{size}x{size}', 'PNG:' + out_file])

    def _make_frame_temp_dir(self):
        frame_tmp_path = os.path.join(self.temp_dir, self._current_sticker_id)
        try:
            os.mkdir(frame_tmp_path)
        except FileExistsError:
            pass
        return frame_tmp_path

    def apng_convert_to_rgba(self, in_file, out_file):
        ffmpeg.input(in_file, f='apng').overwrite_output(
                out_file, pix_fmt='rgba', f='apng').run(quiet=True)

    def split_apng_frames(self, in_file, frame_dir):
        # split frames using imagemagick
        subprocess.call(
                [_MAGICK_BIN, 'APNG:' + in_file, '-coalesce', os.path.join(frame_dir, 'frame-%02d.png')])

    def _make_frame_file(self, durations, frame_working_dir_path):
        with open(os.path.join(frame_working_dir_path, 'frames.txt'), 'w') as f:
            for i, d in enumerate(durations):
                f.write(f"file 'frame-{i:02d}.png'\n")
                f.write(f'duration {d}\n')
            # last frame need to be put twice, see: https://trac.ffmpeg.org/wiki/Slideshow
            # f.write(f"file 'frame-{len(durations) - 1}.png'\n")
        return os.path.join(frame_working_dir_path, 'frames.txt')

    def to_webm(self, durations, frame_dir, out_file):
        # framerate is needed here since telegram ios client will use framerate as play speed
        # in fact, framerate in webm should be informative only
        # ffmpeg will use 25 by default, here according to telegram we use 30
        # so we set vsync=1 (cfr), let ffmpeg duplicate some frames to make ios happy
        # this will cause file size to increase a bit, but it should be OK
        # also 1/framerate seems to be the minimum unit of ffmpeg to encode frame duration
        # so shouldn't set it too small - which will cause too much error
        # https://bugs.telegram.org/c/14778

        frame_file_path = self._make_frame_file(durations, frame_dir)

        ffmpeg.input(frame_file_path, format='concat') \
            .output(out_file, r=30, fps_mode='cfr', f='webm') \
            .overwrite_output() \
            .run(quiet=False)

    def get_animation_delays(self, in_apng):

        p = subprocess.Popen(
                [_MAGICK_BIN, 'identify', '-format', r'%T,', 'APNG:' + in_apng],
                stdin=None, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, shell=False)
        out, err = p.communicate()
        frame_data_str_output = out.decode().strip()[:-1]
        delays = [round(int(i) / 100, 3) for i in frame_data_str_output.split(',')]
        return delays

    def probe_duration(self, file):
        duration_str = ffmpeg.probe(file)['streams'][0]['tags']['DURATION']

        hms, us = duration_str.split('.')
        us = us[:6]
        duration_str = f'{hms}.{us}'
        duration_dt = datetime.datetime.strptime(duration_str, '%H:%M:%S.%f')
        duration_seconds = datetime.timedelta(seconds=duration_dt.second,
                                              microseconds=duration_dt.microsecond).total_seconds()
        return duration_seconds

    def cap_webm_duration_and_size(self, durations, in_webm, frame_dir, out_file):
        # TODO even after optimization, webm file size may still exceed the limit. Lossy compression may be needed
        print('Cap webm duration and size')
        # probe duration, ensure it's max 3 seconds
        duration_seconds = self.probe_duration(in_webm)

        if duration_seconds > WEBM_DURATION_SEC_MAX:
            factor = duration_seconds / WEBM_DURATION_SEC_MAX
            while True:
                # loop to reduce frame duration until it's less than WEBM_DURATION_SEC_MAX seconds
                new_delays = [int(d / factor * 1000) / 1000 for d in durations]
                print('New delays: ', new_delays)
                self.to_webm(new_delays, frame_dir, out_file)
                new_duration_seconds = self.probe_duration(file=out_file)
                if new_duration_seconds > WEBM_DURATION_SEC_MAX:
                    print(f'WARNING: Duration too long, cap again: {new_duration_seconds} seconds')
                    factor = factor * 1.05
                else:
                    break
        else:  # just copy
            shutil.copyfile(in_webm, out_file)

        # see if file size is OK
        if os.path.getsize(out_file) > WEBM_SIZE_KB_MAX * 1024:
            # TODO optimize file size
            with _print_lock:
                print(f'WARNING: File size too large, {os.path.getsize(out_file) / 1024} KB')

    def remove_alpha(self, in_file, out_file):
        if self._sticker_has_animation:
            ffmpeg.input(in_file, f='apng').filter('geq',
                                                   r='(r(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                                                   g='(g(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                                                   b='(b(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                                                   a=255).output(out_file, f='apng',
                                                                 pix_fmt='rgb24').overwrite_output().run(quiet=True)
        else:
            # use magick for static image
            subprocess.call(
                    ['magick', 'convert', 'PNG:' + in_file, '-background', 'white', '-alpha', 'remove', '-alpha', 'off',
                     'PNG:' + out_file])

    def to_gif(self, in_file, out_file):
        if self._sticker_has_animation:
            f = 'apng'
        else:
            f = 'image2'
        palette_stream = ffmpeg.input(in_file, f=f).filter('palettegen', reserve_transparent=1)
        ffmpeg.filter([ffmpeg.input(in_file, f=f), palette_stream], 'paletteuse',
                      alpha_threshold=GIF_ALPHA_THRESHOLD) \
            .output(out_file, f='gif') \
            .overwrite_output() \
            .run(quiet=True)
        # issue with tencent qq/tim
        subprocess.call(['magick', out_file, '-coalesce', out_file])

    def to_video(self, in_pic, in_audio, out_file):
        streams = []
        in_pic_stream = ffmpeg.input(in_pic, f='apng').filter('pad',
                                                              w='ceil(iw/2)*2',
                                                              h='ceil(ih/2)*2'  # make w,h divisible b 2, enable H.264
                                                              )
        streams.append(in_pic_stream)
        if in_audio:
            audio_input = ffmpeg.input(in_audio)
            streams.append(audio_input)
        ffmpeg.output(*streams, out_file, pix_fmt='yuv420p', movflags='faststart') \
            .overwrite_output().run(quiet=True)


def process_sticker_icon(in_file, out_file):
    ffmpeg.input(in_file, f='apng') \
        .filter('scale', w='if(gt(iw,ih),100,-1)', h='if(gt(iw,ih),-1,100)') \
        .filter('pad', w='100', h='100', x='(ow-iw)/2', y='(oh-ih)/2', color='black@0') \
        .output(out_file).overwrite_output().run(quiet=True)
