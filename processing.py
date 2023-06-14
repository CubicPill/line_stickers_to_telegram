import datetime
import math
import os.path
import queue
import shutil
import subprocess
import traceback
from enum import Enum
from threading import Thread

import ffmpeg

from utils import StickerType, sticker_type_properties

MAGICK_BIN = shutil.which('magick')


class OutputFormat(Enum):
    # this will also be the file extension
    GIF = 'gif'
    WEBM = 'webm'
    VIDEO = 'mp4'
    APNG = 'png'


class Operation(Enum):
    SCALE = 'scale'
    OVERLAY = 'overlay'
    TO_GIF = 'to_gif'
    TO_WEBM = 'to_webm'
    # TO_VIDEO = 'to_video'


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

    def run(self):
        while not self.queue.empty():
            try:
                task: ProcessTask = self.queue.get_nowait()
            except queue.Empty:
                continue
            self._current_sticker_id = task.sticker_id
            try:
                curr_in = task.in_img
                for i, op in enumerate(task.operations):
                    curr_out = os.path.join(self.temp_dir, f'{self._current_sticker_id}_interim_{i}.tmp')
                    if op == Operation.SCALE:
                        self.scale_image(curr_in, curr_out, task.scale_px)
                    elif op == Operation.OVERLAY:
                        self.overlay_sticker_message(curr_in, task.in_overlay, curr_out)
                    elif op == Operation.TO_GIF:
                        self.to_gif(curr_in, curr_out)
                    elif op == Operation.TO_WEBM:
                        self.to_webm(curr_in, curr_out)
                    # elif op == Operation.TO_VIDEO:
                    #     self.to_video()
                    curr_in = curr_out
                shutil.copy(curr_in, task.result_path)
            except ffmpeg.Error as e:
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

    def overlay_sticker_message(self, in_img, in_overlay, out_file):
        # overlay in_overlay on in_img
        subprocess.call([MAGICK_BIN, in_img, in_overlay, '-gravity', 'center', '-composite', out_file])

    def scale_image(self, in_file, out_file, size):
        has_animation, _, _, _, _ = sticker_type_properties(self.sticker_type)
        if has_animation:
            ffmpeg.input(in_file, f='apng').filter('scale', w=f'if(gt(iw,ih),{size},-1)',
                                                   h=f'if(gt(iw,ih),-1,{size})').output(
                    out_file, pix_fmt='rgba', f='apng').run(quiet=True)
        else:
            subprocess.call([MAGICK_BIN, in_file, '-resize', f'{size}x{size}', out_file])

    def _make_frame_temp_dir(self, uid):
        frame_tmp_path = os.path.join(self.temp_dir, uid)
        try:
            os.mkdir(frame_tmp_path)
        except FileExistsError:
            pass
        return frame_tmp_path

    def apng_convert_to_rgba(self, in_file, out_file):
        ffmpeg.input(in_file, f='apng').overwrite_output(
                out_file, pix_fmt='rgba', f='apng').run(quiet=True)

    def to_webm(self, in_file, out_file):
        # TODO verify the framerate
        # kakao and here both split and rejoin frames
        # however from line apng there's no issue with play speed -p
        try:
            pix_fmt = ffmpeg.probe(in_file)['streams'][0]['pix_fmt']
        except KeyError:
            pix_fmt = 'unknown'
        # convert non-rgba to rgba
        if pix_fmt != 'rgba':
            rgba_interim_apng = os.path.join(self.temp_dir, f'{self._current_sticker_id}.rgba.png')
            self.apng_convert_to_rgba(in_file, rgba_interim_apng)
        else:
            rgba_interim_apng = in_file
        # if pix_fmt == 'pal8':
        #     # need to split frames, convert color, then replace in_file
        #     frame_tmp_path = self._make_frame_temp_dir(task.id)
        #
        #     framerate_str = ffmpeg.probe(task.current_in_file_path)['streams'][0]['r_frame_rate']
        #     framerate = round(int(framerate_str.split('/')[0]) / int(framerate_str.split('/')[1]))
        #
        #     ffmpeg.input(task.current_in_file_path, f='apng'). \
        #         output(os.path.join(frame_tmp_path, 'frame-convert-%d.png'), start_number=0) \
        #         .overwrite_output(). \
        #         run(quiet=True)
        #
        #     for fn in os.listdir(frame_tmp_path):
        #         if fn.startswith('frame-convert'):
        #             # convert color to rgba
        #             fn_full = os.path.join(frame_tmp_path, fn)
        #             image = Image.open(fn_full)
        #             image = image.convert('RGBA')
        #             image.save(fn_full)
        #     ffmpeg.input(os.path.join(frame_tmp_path, 'frame-convert-%d.png'),
        #                  start_number=0, framerate=framerate, ) \
        #         .output(task.current_out_file_path, f='apng') \
        #         .overwrite_output() \
        #         .run(quiet=True)
        #     task.step_done()
        raw_output_file = os.path.join(self.temp_dir, f'{self._current_sticker_id}.raw.webm')

        ffmpeg.input(rgba_interim_apng, f='apng').output(raw_output_file).overwrite_output().run(quiet=True)
        capped_webm = os.path.join(self.temp_dir, f'{self._current_sticker_id}.cap.webm')
        if not self.cap_webm_duration_and_size(raw_output_file, rgba_interim_apng, capped_webm):
            capped_webm = raw_output_file
        shutil.copy(capped_webm, out_file)

    def cap_webm_duration_and_size(self, in_webm, in_apng, out_file):
        # probe, ensure it's max 3 seconds
        # length is not accurate in apng, must probe converted webm
        SIZE_KB_MAX = 256
        DURATION_SEC_MAX = 3
        size_kb = os.path.getsize(in_webm) / 1024
        duration_str = ffmpeg.probe(in_webm)['streams'][0]['tags']['DURATION']
        framerate_str = ffmpeg.probe(in_webm)['streams'][0]['r_frame_rate']
        framerate = round(int(framerate_str.split('/')[0]) / int(framerate_str.split('/')[1]))

        hms, us = duration_str.split('.')
        us = us[:6]
        duration_str = f'{hms}.{us}'
        duration_dt = datetime.datetime.strptime(duration_str, '%H:%M:%S.%f')
        duration_seconds = datetime.timedelta(seconds=duration_dt.second,
                                              microseconds=duration_dt.microsecond).total_seconds()
        total_frames = round(duration_seconds * framerate)

        if duration_seconds > DURATION_SEC_MAX:
            # need to speedup: split image to frames and re-generate

            new_framerate = math.ceil((total_frames + 1) / 3)

            frame_tmp_path = self._make_frame_temp_dir(self._current_sticker_id)

            ffmpeg.input(in_apng, f='apng').output(os.path.join(frame_tmp_path, 'frame-%d.png'),
                                                   start_number=0).overwrite_output().run(
                    quiet=True)
            ffmpeg.input(os.path.join(frame_tmp_path, 'frame-%d.png'), start_number=0, framerate=new_framerate,
                         ).output(out_file).overwrite_output().run(quiet=True)
            return True
        return False

    def remove_alpha(self, in_file, out_file):
        ffmpeg.input(in_file, f='apng').filter('geq',
                                               r='(r(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                                               g='(g(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                                               b='(b(X,Y)*alpha(X,Y)/255)+(255-alpha(X,Y))',
                                               a=255).output(out_file, f='apng').overwrite_output().run(quiet=True)

    def to_gif(self, in_file, out_file):
        noalpha_interim_apng = os.path.join(self.temp_dir, f'{self._current_sticker_id}.noalpha.png')
        self.remove_alpha(in_file, noalpha_interim_apng)

        palette_stream = ffmpeg.input(noalpha_interim_apng, f='apng').filter('palettegen')
        ffmpeg.filter([ffmpeg.input(noalpha_interim_apng, f='apng'), palette_stream], 'paletteuse') \
            .output(out_file, f='gif') \
            .overwrite_output() \
            .run(quiet=True)

    def to_video(self, in_pic, in_audio, out_file):
        raise NotImplementedError
        # disable for now
        # streams = list()
        # pix_fmt = ffmpeg.probe(in_pic)['streams'][0]['pix_fmt']
        # in_pic_stream = ffmpeg.input(in_pic, f='apng')
        # video_output = self.remove_alpha(in_pic_stream, pix_fmt) \
        #     .filter('scale',
        #             w='trunc(iw/2)*2',
        #             h='trunc(ih/2)*2'  # enable H.264
        #             )
        #
        # streams.append(video_output)
        # if in_audio:
        #     audio_input = ffmpeg.input(in_audio)
        #     streams.append(audio_input)
        # ffmpeg.output(*streams, out_file, pix_fmt='yuv420p', movflags='faststart') \
        #     .overwrite_output().run(quiet=True)


def process_sticker_icon(in_file, out_file):
    ffmpeg.input(in_file, f='apng') \
        .filter('scale', w='if(gt(iw,ih),100,-1)', h='if(gt(iw,ih),-1,100)') \
        .filter('pad', w='100', h='100', x='(ow-iw)/2', y='(oh-ih)/2', color='black@0') \
        .output(out_file).overwrite_output().run(quiet=True)
