import argparse
import os
import re
import time
from queue import Queue

import requests
from tqdm import tqdm

from processing import ImageProcessorThread, ProcessOption
from spider import DownloadThread
from utils import SET_URL_TEMPLATE, parse_page, StickerType, STICKER_URL_TEMPLATES

proxies = {}


def main():
    arg_parser = argparse.ArgumentParser(description='Download stickers from line store')
    arg_parser.add_argument('id', type=int, help='Product id of sticker set')
    arg_parser.add_argument('--proxy', type=str, help='HTTPS proxy, addr:port')
    arg_parser.add_argument('--no-scale', help='Disable static stickers auto resizing to 512*512', action='store_false')
    arg_parser.add_argument('--static', help='Download only static images. Will override all other conversion options',
                            action='store_true')
    arg_parser.add_argument('--to-gif', help='Convert animated PNG (.apng) to GIF', action='store_true')
    arg_parser.add_argument('--to-video',
                            help='Convert sticker (static/animated/popup) to .mp4 video, with audio (if available). Static stickers without audio cannot be converted to video',
                            action='store_true')
    arg_parser.add_argument('-p', '--path', type=str, help='Path to download the stickers')
    arg_parser.add_argument('-t', '--threads', type=int, help='Thread number of downloader, default 4')
    args = arg_parser.parse_args()
    if args.proxy:
        proxies['https'] = args.proxy
    thread_num = args.threads or 4
    r = requests.get(SET_URL_TEMPLATE.format(id=args.id), proxies=proxies)
    title, id_list, sticker_type = parse_page(r.content)
    if args.static:
        sticker_type = StickerType.STATIC_STICKER
    title = '_'.join(re.sub(r'[/:*?"<>|]', '', title).split())
    # remove invalid characters in folder name
    if args.path:
        path = args.path
    else:
        path = title
    if not os.path.isdir(path):
        os.mkdir(path)
    os.mkdir(path + os.path.sep + 'tmp')

    option = ProcessOption.SCALE
    if args.to_video:
        option = ProcessOption.TO_VIDEO
    elif args.to_gif:
        option = ProcessOption.TO_GIF
    elif args.no_scale:
        option = ProcessOption.NONE
    download_queue = Queue()
    process_queue = Queue()
    downloader = [DownloadThread(download_queue) for _ in range(thread_num)]

    for _id in id_list:
        filename = path + '/{fn}_{t}.png'.format(fn=_id, t=sticker_type)
        url = STICKER_URL_TEMPLATES[sticker_type].format(id=_id)
        download_queue.put((url, filename, sticker_type))
        if sticker_type in [StickerType.STATIC_WITH_SOUND_STICKER, StickerType.ANIMATED_AND_SOUND_STICKER,
                            StickerType.POPUP_AND_SOUND_STICKER]:
            filename = path + '/{fn}.m4a'.format(fn=_id)
            url = STICKER_URL_TEMPLATES[StickerType.SOUND].format(id=_id)
            download_queue.put((url, filename, sticker_type))

    for d in downloader:
        d.start()
    if option == ProcessOption.NONE:
        pass
    processor = [ImageProcessorThread(process_queue, option) for _ in range(4)]
    with tqdm(total=len(id_list)) as bar:
        last = len(id_list)
        while not download_queue.empty():
            bar.update(last - download_queue.qsize())
            last = download_queue.qsize()
            time.sleep(0.1)
        download_queue.join()
        bar.clear()
    print('All done!')


if __name__ == '__main__':
    main()
