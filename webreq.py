import os
import re
from threading import Thread

import requests
from bs4 import BeautifulSoup

from utils import (
    EMOJI_SET_META_URL,
    FAKE_HEADERS,
    PackNotFoundException,
    STICKER_SET_META_URL,
    STICKER_SET_URL_TEMPLATES,
    STICKER_ZIP_TEMPLATES,
    SourceUrlType,
    StickerType,
    increase_counter,
)

_proxies = None


def set_proxy(proxies):
    global _proxies
    _proxies = proxies


def download_file(url, filename, overwrite=False):
    if os.path.isfile(filename) and not overwrite:
        # file exist
        return
    r = requests.get(url, proxies=_proxies, headers=FAKE_HEADERS)
    with open(filename, "wb") as f:
        f.write(r.content)


def get_real_pack_id_from_yabe_emoji(pack_id):
    r = requests.get(
        STICKER_SET_URL_TEMPLATES[SourceUrlType.YABE_EMOJI].format(pack_id=pack_id),
        proxies=_proxies,
        headers=FAKE_HEADERS,
    )
    soup = BeautifulSoup(r.content, "html5lib")
    if match := re.search(r"line.me/S/emoji/\?id=([a-f0-9]+)", soup.text):
        pack_id = match.group(1)
    else:
        raise ValueError("Unable to locate pack id!")
    return pack_id


def get_sticker_info_from_line_page(pack_id, is_emoji, lang):
    url = (
        STICKER_SET_URL_TEMPLATES[SourceUrlType.LINE_EMOJI].format(
            pack_id=pack_id, lang=lang
        )
        if is_emoji
        else STICKER_SET_URL_TEMPLATES[SourceUrlType.LINE].format(
            pack_id=pack_id, lang=lang
        )
    )
    r = requests.get(url, proxies=_proxies, headers=FAKE_HEADERS)
    soup = BeautifulSoup(r.content, "html5lib")
    if soup.select_one('[data-test="not-on-sale-description"]'):
        # the sticker is not available, maybe due to region restriction or no longer available
        # we can still get title and head image though
        title = soup.select_one("div.mdMN05Img img").attrs["alt"]
        print(
            f"WARNING: Pack {pack_id} is not on sale, title: {title}, skipping author data"
        )
        return title, None, None
    if is_emoji:
        title = soup.select_one('p[data-test="emoji-name-title"]').text
        author_name = soup.select_one('a[data-test="emoji-author"]').text
        author_id = re.search(
            r"author/(\d+)",
            soup.select_one('a[data-test="emoji-author"]').attrs["href"],
        ).group(1)
    else:
        if soup.select_one('p[data-test="sticker-name-title"]'):
            title = soup.select_one('p[data-test="sticker-name-title"]').text
            author_name = soup.select_one('a[data-test="sticker-author"]').text
        elif soup.select_one('h3[data-test="oa-sticker-title"]'):
            title = soup.select_one('h3[data-test="oa-sticker-title"]').text
            author_name = soup.select_one('p[data-test="oa-sticker-author"]').text
        else:
            raise ValueError("Unable to locate sticker title!")
        if soup.select_one('a[data-test="sticker-author"]'):
            author_id = re.search(
                r"author/(\d+)",
                soup.select_one('a[data-test="sticker-author"]').attrs["href"],
            ).group(1)
        else:
            author_id = None
    return title, author_name, author_id


def get_metadata(pack_id: str, is_emoji: bool) -> dict:
    if is_emoji:
        metadata_url = EMOJI_SET_META_URL.format(pack_id=pack_id)
    else:
        metadata_url = STICKER_SET_META_URL.format(pack_id=pack_id)
    r = requests.get(metadata_url, proxies=_proxies, headers=FAKE_HEADERS)
    if r.status_code == 404:
        raise PackNotFoundException(f"Sticker pack {pack_id} not found!")
    return r.json()


def get_sticker_archive(pack_id, sticker_type: StickerType):
    url = STICKER_ZIP_TEMPLATES[sticker_type].format(pack_id=pack_id)
    r = requests.get(url, proxies=_proxies, headers=FAKE_HEADERS)
    return r.content


class MultiThreadDownloader(Thread):
    def __init__(self, queue, overwrite=False):
        Thread.__init__(self, name="DownloadThread")
        self.queue = queue
        self.overwrite = overwrite

    def run(self):
        while not self.queue.empty():
            _id, url, path = self.queue.get()
            try:
                download_file(url, path, overwrite=self.overwrite)
            except requests.RequestException:
                self.queue.put((_id, url, path))

            else:
                increase_counter()
            finally:
                self.queue.task_done()
                increase_counter()
