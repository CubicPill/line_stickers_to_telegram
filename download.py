import argparse
import os
import re
import shutil
import time
from queue import Queue

import requests
from tqdm import tqdm

from parse import parse_page
from processing import ImageProcessorThread, ProcessOption
from spider import DownloadThread
from utils import SET_URL_TEMPLATES, STICKER_URL_TEMPLATES, StickerType, StickerSetSource


def main():
    arg_parser = argparse.ArgumentParser(description='Download stickers from line store')
    arg_parser.add_argument('id', type=int, help='Product id of sticker set')
    arg_parser.add_argument('--source', type=str, help='Source to get sticker set information. Default is "line"')
    arg_parser.add_argument('--lang', type=str,
                            help='Language(Zone) to get sticker. Could be "en", "ja", "zh-Hant" and others. Default is "en"')
    arg_parser.add_argument('--proxy', type=str, help='HTTPS proxy, addr:port')
    arg_parser.add_argument('--no-scale', help='Disable static stickers auto resizing to 512*512', action='store_false')
    arg_parser.add_argument('--static',
                            help='Download only static images (Will preserve APNG). Will override all other conversion options',
                            action='store_true')
    arg_parser.add_argument('--to-gif', help='Convert animated PNG (.apng) to GIF', action='store_true')
    arg_parser.add_argument('--to-video',
                            help='Convert sticker (static/animated/popup) to .mp4 video, with audio (if available). Static stickers without audio cannot be converted to video',
                            action='store_true')
    arg_parser.add_argument('-p', '--path', type=str, help='Path to download the stickers')
    arg_parser.add_argument('-t', '--threads', type=int, help='Thread number of downloader, default 4')
    args = arg_parser.parse_args()
    proxies = {}
    if args.proxy:
        proxies['https'] = args.proxy
    thread_num = args.threads or 4
    source = StickerSetSource.LINE
    if args.source == 'yabe':
        source = StickerSetSource.YABE
    lang = 'en'
    if args.lang:
        lang = args.lang
    r = requests.get(SET_URL_TEMPLATES[source].format(id=args.id, lang=lang), proxies=proxies)
    title, id_list, sticker_type = parse_page(r.content, source)
    if args.static:
        sticker_type = StickerType.STATIC_STICKER
    title = '_'.join(re.sub(r'[/:*?"<>|]', '', title).split())
    print('Title:', title)
    print('Sticker Type:', sticker_type.name)
    print('Total number of stickers:', len(id_list))
    # remove invalid characters in folder name
    if args.path:
        path = args.path
    else:
        path = title
    if not os.path.isdir(path):
        os.mkdir(path)
    if not os.path.isdir(path + os.path.sep + 'tmp'):
        os.mkdir(path + os.path.sep + 'tmp')
    print('Downloading to:', path)
    option = ProcessOption.SCALE
    if args.to_video:
        option = ProcessOption.TO_VIDEO
    elif args.to_gif:
        option = ProcessOption.TO_GIF
    elif args.no_scale:
        option = ProcessOption.NONE
    download_queue = Queue()
    download_completed_queue = Queue()
    downloader = [DownloadThread(download_queue, download_completed_queue, proxies) for _ in range(thread_num)]
    for _id in id_list:
        if option == ProcessOption.NONE:

            filename = os.path.sep.join([path, '{fn}_{t}.png'.format(fn=_id, t=sticker_type.name)])
        else:
            filename = os.path.sep.join([path, 'tmp', '{fn}_{t}.png'.format(fn=_id, t=sticker_type)])

        url = STICKER_URL_TEMPLATES[sticker_type].format(id=_id)
        download_queue.put((_id, url, filename))
        if sticker_type in [StickerType.STATIC_WITH_SOUND_STICKER,
                            StickerType.ANIMATED_AND_SOUND_STICKER,
                            StickerType.POPUP_AND_SOUND_STICKER] \
                and option == ProcessOption.TO_VIDEO:
            filename = os.path.sep.join([path, 'tmp', '{fn}.m4a'.format(fn=_id)])
            url = STICKER_URL_TEMPLATES[StickerType.SOUND].format(id=_id)
            download_queue.put(('{}|Audio'.format(_id), url, filename))

    for d in downloader:
        d.start()
    if sticker_type in [StickerType.STATIC_WITH_SOUND_STICKER,
                        StickerType.ANIMATED_AND_SOUND_STICKER,
                        StickerType.POPUP_AND_SOUND_STICKER] \
            and option == ProcessOption.TO_VIDEO:

        total_count = len(id_list) * 2
    else:
        total_count = len(id_list)
    with tqdm(total=total_count) as bar:
        last = total_count
        while not download_queue.empty():
            bar.update(last - download_queue.qsize())
            last = download_queue.qsize()
            time.sleep(0.1)
        download_queue.join()
        bar.clear()

    print('Download done!')

    if option != ProcessOption.NONE:
        print('Processing:', option.name)
        process_queue = Queue()
        while not download_completed_queue.empty():
            _id = download_completed_queue.get_nowait()
            if 'Audio' in _id:
                continue
            if option == ProcessOption.TO_VIDEO:
                in_pic = os.path.sep.join([path, 'tmp', '{fn}_{t}.png'.format(fn=_id, t=sticker_type)])
                in_audio = os.path.sep.join([path, 'tmp', '{fn}.m4a'.format(fn=_id)])
                if not os.path.isfile(in_audio):
                    in_audio = None
                out_file = os.path.sep.join([path, '{fn}.mp4'.format(fn=_id)])
                process_queue.put_nowait((in_pic, in_audio, out_file))

            else:
                in_file = os.path.sep.join([path, 'tmp', '{fn}_{t}.png'.format(fn=_id, t=sticker_type)])
                out_file = os.path.sep.join([path, '{fn}.gif'.format(fn=_id)])
                process_queue.put_nowait((in_file, out_file))
        processor = [ImageProcessorThread(process_queue, option, path + os.path.sep + 'tmp') for _ in range(4)]
        for p in processor:
            p.start()
        with tqdm(total=total_count) as bar:
            last = total_count
            while not download_queue.empty() or not process_queue.empty():
                bar.update(last - max(download_queue.qsize(), process_queue.qsize()))
                last = max(download_queue.qsize(), process_queue.qsize())
                time.sleep(0.1)
            download_queue.join()
            process_queue.join()
            bar.clear()
        print('Process done!')
        shutil.rmtree(path + os.path.sep + 'tmp')


if __name__ == '__main__':
    main()
