import re
from enum import Enum

from PIL import Image
from bs4 import BeautifulSoup

SINGLE_STICKER_ID_PATTERN = re.compile(r'stickershop/v1/sticker/(\d+)/\w+/sticker.png')


class StickerType(Enum):
    STATIC_STICKER = 'static'
    ANIMATED_STICKER = 'animated'
    POPUP_STICKER = 'popup'
    STATIC_WITH_SOUND_STICKER = 'static&sound'
    ANIMATED_AND_SOUND_STICKER = 'animated&sound'
    POPUP_AND_SOUND_STICKER = 'popup&sound'
    SOUND = 'sound'


SET_URL_TEMPLATE = 'https://store.line.me/stickershop/product/{id}/en?from=sticker'

STICKER_URL_TEMPLATES = {
    StickerType.SOUND: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_sound.m4a',
    StickerType.STATIC_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/android/sticker@2x.png',
    StickerType.STATIC_WITH_SOUND_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/android/sticker@2x.png',
    StickerType.ANIMATED_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_animation@2x.png',
    StickerType.ANIMATED_AND_SOUND_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_animation@2x.png',
    StickerType.POPUP_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_popup@2x.png',
    StickerType.POPUP_AND_SOUND_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_popup@2x.png'
}
FAKE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36'
}


def parse_page(content: bytes):
    sticker_type = StickerType.STATIC_STICKER
    soup = BeautifulSoup(content, 'html5lib')
    sticker_list = soup.find_all('span', {'class': 'mdCMN09Image'})
    if soup.find('span', {'class': 'MdIcoFlash_b'}):
        sticker_type = StickerType.POPUP_STICKER
    elif soup.find('span', {'class': 'MdIcoFlashAni_b'}):
        sticker_type = StickerType.POPUP_AND_SOUND_STICKER
    elif soup.find('span', {'class': 'MdIcoPlay_b'}):
        sticker_type = StickerType.ANIMATED_STICKER
    elif soup.find('span', {'class': 'MdIcoFlash_b'}):
        sticker_type = StickerType.ANIMATED_AND_SOUND_STICKER
    elif soup.find('span', {'class': 'MdIcoSound_b'}):
        sticker_type = StickerType.STATIC_WITH_SOUND_STICKER

    title = soup.find('h3', {'class': 'mdCMN08Ttl'}).text
    id_list = list()
    for sticker in sticker_list:
        match = SINGLE_STICKER_ID_PATTERN.search(sticker['style'])
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
