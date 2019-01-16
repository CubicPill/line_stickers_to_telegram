import argparse
import os
import re
import time
from queue import Queue
from threading import Thread

import requests
from PIL import Image
from bs4 import BeautifulSoup
from tqdm import tqdm

# TODO: Download sounds, convert APNG to GIF / Video(with sounds)
PATTERN = re.compile(r'stickershop/v1/sticker/(\d+)/\w+/sticker.png')
STATIC_STICKER = 'static'
ANIMATED_STICKER = 'animated'
ANIMATED_AND_SOUND_STICKER = 'animated&sound'
POPUP_STICKER = 'popup'
POPUP_AND_SOUND_STICKER = 'popup&sound'
SOUND_ONLY_STICKER = 'sound_only'
SOUND = 'sound'
SET_URL_TEMPLATE = 'https://store.line.me/stickershop/product/{id}/en?from=sticker'
STICKER_URL_TEMPLATES = {
    SOUND: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_sound.m4a',
    STATIC_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/android/sticker@2x.png',
    SOUND_ONLY_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/android/sticker@2x.png',
    ANIMATED_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_animation@2x.png',
    ANIMATED_AND_SOUND_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_animation@2x.png',
    POPUP_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_popup@2x.png',
    POPUP_AND_SOUND_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_popup@2x.png'
}
proxies = {}
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36'
}


def parse_page(content: bytes):
    sticker_type = STATIC_STICKER
    soup = BeautifulSoup(content, 'html5lib')
    sticker_list = soup.find_all('span', {'class': 'mdCMN09Image'})
    if soup.find('span', {'class': 'MdIcoFlash_b'}):
        sticker_type = POPUP_STICKER
    elif soup.find('span', {'class': 'MdIcoFlashAni_b'}):
        sticker_type = POPUP_AND_SOUND_STICKER
    elif soup.find('span', {'class': 'MdIcoPlay_b'}):
        sticker_type = ANIMATED_STICKER
    elif soup.find('span', {'class': 'MdIcoFlash_b'}):
        sticker_type = ANIMATED_AND_SOUND_STICKER
    elif soup.find('span', {'class': 'MdIcoSound_b'}):
        sticker_type = SOUND_ONLY_STICKER

    title = soup.find('h3', {'class': 'mdCMN08Ttl'}).text
    id_list = list()
    for sticker in sticker_list:
        match = PATTERN.search(sticker['style'])
        if match:
            id_list.append(match.group(1))

    return title, id_list, sticker_type


def scale_image(path):
    # TODO: handle this with ffmpeg?
    img = Image.open(path)
    w, h = img.size
    if max([w, h]) == 512:
        return
    if w > h:
        w_s, h_s = 512, int(h / w * 512)
    else:
        w_s, h_s = int(w / h * 512), 512
    img.resize((w_s, h_s), Image.ANTIALIAS).save(path)


def download_file(url, filename):
    print(url)
    r = requests.get(url, proxies=proxies, headers=headers)
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
                if sticker_type == STATIC_STICKER and scale:
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
        sticker_type = STATIC_STICKER
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
        if sticker_type in [SOUND_ONLY_STICKER, ANIMATED_AND_SOUND_STICKER, POPUP_AND_SOUND_STICKER]:
            filename = path + '/{fn}.m4a'.format(fn=_id)
            url = STICKER_URL_TEMPLATES[SOUND].format(id=_id)
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
