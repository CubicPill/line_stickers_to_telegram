import requests
from bs4 import BeautifulSoup
import re
import os
from PIL import Image
from queue import Queue
from threading import Thread
import argparse
import time
from tqdm import tqdm

PATTERN = re.compile(r'stickershop/v1/sticker/(\d+)/\w+/sticker.png')
SET_URL_TEMPLATE = 'https://store.line.me/stickershop/product/{id}/en?from=sticker'
STICKER_URL_TEMPLATE = 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/android/sticker.png'
proxies = {}


def parse_page(content: bytes):
    soup = BeautifulSoup(content, 'html5lib')
    sticker_list = soup.find_all('span', {'class': 'mdCMN09Image'})
    title = soup.find('h3', {'class': 'mdCMN08Ttl'}).text
    id_list = list()
    for sticker in sticker_list:
        match = PATTERN.search(sticker['style'])
        if match:
            id_list.append(match.group(1))

    return title, id_list


def scale_image(path):
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
    r = requests.get(url, stream=True, proxies=proxies)
    with open(filename, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)


class Downloader(Thread):
    def __init__(self, queue: Queue):
        Thread.__init__(self)
        self.queue = queue

    def run(self):
        while not self.queue.empty():
            (url, path, scale) = self.queue.get()
            try:
                download_file(url, path)
                if scale:
                    scale_image(path)
            except requests.RequestException as e:
                print(e)
                self.queue.put((url, path, scale))
            finally:
                self.queue.task_done()


def main():
    scale = True
    arg_parser = argparse.ArgumentParser(description='Download stickers from line store')
    arg_parser.add_argument('id', type=int, help='Product id of sticker set')
    arg_parser.add_argument('--proxy', type=str, help='HTTPS proxy, addr:port')
    arg_parser.add_argument('--noscale', help='Disable auto resize to 512*512', action='store_false')
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
    title, id_list = parse_page(r.content)
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
        filename = path + '/{fn}.png'.format(fn=_id)
        url = STICKER_URL_TEMPLATE.format(id=_id)
        queue.put((url, filename, scale))
    for d in downloader:
        d.start()
    with tqdm(total=len(id_list)) as bar:
        last = len(id_list)
        while not queue.empty():
            bar.update(last - queue.qsize())
            last = queue.qsize()
            time.sleep(0.1)
        bar.clear()
    print('All done!')


if __name__ == '__main__':
    main()
