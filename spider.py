import argparse
import os
import re
import time
from queue import Queue
from threading import Thread

import requests
from tqdm import tqdm

# TODO: Download sounds, convert APNG to GIF / Video(with sounds)
from utils import SET_URL_TEMPLATE, STICKER_URL_TEMPLATES, FAKE_HEADERS, parse_page, scale_image, StickerType

proxies = {}


def download_file(url, filename):
    print(url)
    r = requests.get(url, proxies=proxies, headers=FAKE_HEADERS)
    with open(filename, 'wb') as f:
        f.write(r.content)


class Downloader(Thread):
    def __init__(self, queue: Queue):
        Thread.__init__(self)
        self.queue = queue

    def run(self):
        while not self.queue.empty():
            (url, path, scale, sticker_type) = self.queue.get()
            try:
                download_file(url, path)
                if sticker_type == StickerType.STATIC_STICKER and scale:
                    scale_image(path)
            except requests.RequestException:
                self.queue.put((url, path, scale, sticker_type))
            finally:
                self.queue.task_done()


class ImageProcessorThread(Thread):
    # TODO: conversion
    pass


def main():
    scale = True
    arg_parser = argparse.ArgumentParser(description='Download stickers from line store')
    arg_parser.add_argument('id', type=int, help='Product id of sticker set')
    arg_parser.add_argument('--proxy', type=str, help='HTTPS proxy, addr:port')
    arg_parser.add_argument('--noscale', help='Disable static stickers auto resizing to 512*512', action='store_false')
    arg_parser.add_argument('--static', help='Download only static images', action='store_true')
    arg_parser.add_argument('-p', '--path', type=str, help='Path to download the stickers')
    arg_parser.add_argument('-t', '--threads', type=int, help='Thread number of downloader, default 4')
    args = arg_parser.parse_args()
    if args.proxy:
        global proxies
        proxies = {'https': args.proxy}
    if args.noscale is False:
        scale = False
    if args.threads:
        thread_num = args.threads
    else:
        thread_num = 4
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
    queue = Queue()
    downloader = [Downloader(queue) for i in range(thread_num)]

    for _id in id_list:
        filename = path + '/{fn}_{t}.png'.format(fn=_id, t=sticker_type)
        url = STICKER_URL_TEMPLATES[sticker_type].format(id=_id)
        queue.put((url, filename, scale, sticker_type))
        if sticker_type in [StickerType.STATIC_WITH_SOUND_STICKER, StickerType.ANIMATED_AND_SOUND_STICKER, StickerType.POPUP_AND_SOUND_STICKER]:
            filename = path + '/{fn}.m4a'.format(fn=_id)
            url = STICKER_URL_TEMPLATES[StickerType.SOUND].format(id=_id)
            queue.put((url, filename, scale, sticker_type))

    for d in downloader:
        d.start()
    with tqdm(total=len(id_list)) as bar:
        last = len(id_list)
        while not queue.empty():
            bar.update(last - queue.qsize())
            last = queue.qsize()
            time.sleep(0.1)
        queue.join()
        bar.clear()
    print('All done!')


if __name__ == '__main__':
    main()
