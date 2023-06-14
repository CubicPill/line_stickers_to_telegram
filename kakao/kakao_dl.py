import argparse
import io
import os
import re
import shutil
import tempfile
import time
import zipfile
from queue import Queue

import requests
from tqdm import tqdm

from decrypt import data_xor
from kakao_process import KakaoWebpProcessor

CHROME_UA_HEADER = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36'}


# for kakao, sticker types are: gif webp png


def get_sticker_id_and_title(url):
    text_content = requests.get(url, headers={'User-Agent': 'Android'}).text
    id_ptn = re.compile(r'kakaotalk://store/emoticon/(\d+)')
    title_ptn = re.compile(r'KakaoTalk Emoticons \| (.+)</title>')
    sticker_id = id_ptn.search(text_content).group(1)
    sticker_title = title_ptn.search(text_content).group(1)

    return sticker_id, sticker_title


def get_sticker_icon_and_name(url):
    resp = requests.get(url, headers=CHROME_UA_HEADER)
    sticker_name = resp.url.split('/')[-1]
    sticker_data_resp = requests.get(f'https://e.kakao.com/api/v1/items/t/{sticker_name}', headers=CHROME_UA_HEADER)
    sticker_icon_url = sticker_data_resp.json()['result']['titleDetailUrl']
    return sticker_icon_url, sticker_name


def main():
    arg_parser = argparse.ArgumentParser(description='Download stickers from Kakao store')
    arg_parser.add_argument('url', type=str, help='URL of sticker set (Kakao share link)')
    arg_parser.add_argument('--proxy', type=str, help='HTTPS proxy, addr:port')
    arg_parser.add_argument('--no-processing', help='No processing', action='store_true')
    arg_parser.add_argument('--static',
                            help='Download only static images.', action='store_true')
    arg_parser.add_argument('--to-gif', help='Convert to GIF, no scaling', action='store_true')
    arg_parser.add_argument('--to-webm',
                            help='Convert to WEBM, to be used in telegram video stickers, will scale to 512*(<512)',
                            action='store_true')
    arg_parser.add_argument('--to-video',
                            help='Convert sticker (animated) to .mp4 video, with audio (if available). No scaling. Static stickers without audio cannot be converted to video',
                            action='store_true')
    arg_parser.add_argument('-p', '--path', type=str, help='Path to download the stickers')
    arg_parser.add_argument('-d', '--debug', help='Enable debug mode', action='store_true')
    arg_parser.add_argument('-t', '--threads', type=int, help='Thread number of downloader, default 4')
    args = arg_parser.parse_args()

    if not args.to_webm:
        print('Sorry, only webm is currently supported')
        raise NotImplementedError

    # check dependency
    if not shutil.which('magick'):
        print('Error: ImageMagick is missing. Please install missing dependencies are re-run the program')
        exit(1)

    proxies = {}
    if args.proxy:
        proxies['https'] = args.proxy

    sticker_url = args.url.strip()
    assert sticker_url.startswith('https://emoticon.kakao.com/items'), 'Invalid URL'

    sticker_id, sticker_title = get_sticker_id_and_title(sticker_url)
    sticker_icon_url, sticker_name = get_sticker_icon_and_name(sticker_url)

    print('Title:', sticker_title)
    print('Name:', sticker_name)

    # remove invalid characters in folder name
    if args.path:
        sticker_root_path = args.path
    else:
        sticker_root_path = f'k{sticker_id}.{sticker_title}'

    sticker_raw_dl_path = os.path.join(sticker_root_path, 'raw')
    sticker_temp_store_path = tempfile.mkdtemp()
    if not os.path.isdir(sticker_root_path):
        os.mkdir(sticker_root_path)
    if not os.path.isdir(sticker_raw_dl_path):
        os.mkdir(sticker_raw_dl_path)

    print('Downloading sticker archive...')

    archive_content = requests.get(f'http://item.kakaocdn.net/dw/{sticker_id}.file_pack.zip', headers=CHROME_UA_HEADER)
    print('Download done!')

    sticker_raw_type = ''
    with zipfile.ZipFile(io.BytesIO(archive_content.content), 'r') as zf:
        sticker_fns = zf.namelist()
        for fn in sticker_fns:
            name, ext = os.path.splitext(fn)
            if ext in [".gif", ".webp"]:
                file_content = data_xor(zf.read(fn))
                if ext == '.webp':
                    sticker_raw_type = 'webp'
            else:
                file_content = zf.read(fn)

            with open(os.path.join(sticker_raw_dl_path, fn), 'wb') as f:
                f.write(file_content)

    total_count = len(sticker_fns)

    print('Processing: Kakao WebP to WebM')

    process_queue = Queue()

    for i, fn in enumerate(sticker_fns):
        uid = os.path.splitext(fn)[0]

        in_pic = os.path.join(sticker_raw_dl_path, fn)

        suffix = 'webm'

        out_file = os.path.sep.join([sticker_root_path, f'{uid}.{suffix}'])
        process_queue.put_nowait((uid, in_pic, out_file))
    num_threads = 4
    if args.debug:
        num_threads = 1
    elif args.threads:
        num_threads = args.threads

    processor = [KakaoWebpProcessor(sticker_temp_store_path, process_queue) for _ in range(num_threads)]
    for p in processor:
        p.start()
    with tqdm(total=total_count) as bar:
        last = total_count
        while not process_queue.empty():
            bar.update(last - process_queue.qsize())
            bar.refresh()
            last = process_queue.qsize()
            time.sleep(0.5)
        process_queue.join()
        bar.n = total_count
        bar.refresh()
        bar.clear()

    print('Process done!')
    # remove temp dir
    if not args.debug:
        shutil.rmtree(sticker_temp_store_path)


if __name__ == '__main__':
    main()
