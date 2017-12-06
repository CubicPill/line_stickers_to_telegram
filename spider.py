import requests
from bs4 import BeautifulSoup
import re
import os
from PIL import Image
import sys
import argparse

PATTERN = re.compile(r'stickershop/v1/sticker/(\d+)/\w+/sticker.png')
url = 'https://store.line.me/stickershop/product/1478946/en?from=sticker'
URL_TEMPLATE = 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/android/sticker.png'
proxies = {'https': '127.0.0.1:1080'}


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


def download_file(url, path):
    r = requests.get(url, stream=True, proxies=proxies)
    with open(path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)


def main():
    scale = True
    arg_parser = argparse.ArgumentParser(description='Download stickers from line store')
    arg_parser.add_argument('id', type=int, help='Product id of sticker set')
    arg_parser.add_argument('--proxy', type=str, help='HTTPS proxy, addr:port')
    arg_parser.add_argument('--noscale', help='Scale the image size to fit telegram stickers', action='store_false')
    arg_parser.add_argument('-p', '--path', type=str, help='Path to download the stickers')
    args = arg_parser.parse_args()
    if args.proxy:
        global proxies
        proxies = {'http': args.proxy}
    if args.noscale is False:
        scale = False
    root_path = args.path or '.'

    r = requests.get(url, proxies=proxies)
    title, id_list = parse_page(r.content)
    title = title.replace(':', ' ')
    # remove invalid characters in folder name
    if not os.path.isdir(title):
        os.mkdir(title)
    for _id in id_list:
        print('downloading {}'.format(_id))
        path = root_path + '/{fd}/{fn}.png'.format(fd=title, fn=_id)
        download_file(URL_TEMPLATE.format(id=_id), path)
        if scale:
            scale_image(path)


if __name__ == '__main__':
    main()
