import re

from bs4 import BeautifulSoup

from utils import StickerType, StickerSetSource


def parse_page(content: bytes, source: StickerSetSource):
    parser = {
        StickerSetSource.YABE: parse_page_yabe,
        StickerSetSource.LINE: parse_page_line
    }
    if source not in parser.keys():
        raise Exception
    return parser[source](content)


def parse_page_yabe(content: bytes):
    sticker_type = StickerType.STATIC_STICKER
    soup = BeautifulSoup(content, 'html5lib')
    talk_icon = soup.select_one('div.stickerData div.talkIcon')
    move_icon = soup.select_one('div.stickerData div.moveIcon')
    popup_icon = soup.select_one('div.stickerData div.PopUpIcon')
    if talk_icon and popup_icon:
        sticker_type = StickerType.POPUP_AND_SOUND_STICKER
    elif popup_icon:
        sticker_type = StickerType.POPUP_STICKER
    elif talk_icon and move_icon:
        sticker_type = StickerType.ANIMATED_AND_SOUND_STICKER
    elif talk_icon:
        sticker_type = StickerType.STATIC_WITH_SOUND_STICKER
    elif move_icon:
        sticker_type = StickerType.ANIMATED_STICKER
    title = soup.select_one('div.stickerData div.title')
    if title:
        title = title.text
    else:
        raise Exception('Error: Title not found')
    id_list = list()
    sticker_id_pattern = re.compile(r'stickershop/v1/sticker/(\d+)/\w+/sticker.png')
    sticker_list = soup.find_all('li', {'class': 'stickerSub'})
    for sticker in sticker_list:
        match = sticker_id_pattern.search(str(sticker))
        if match:
            id_list.append(match.group(1))
    return title, id_list, sticker_type


def parse_page_line(content: bytes):
    sticker_type = StickerType.STATIC_STICKER
    soup = BeautifulSoup(content, 'html5lib')
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

    title = soup.find('p', {'class': 'mdCMN38Item01Ttl'})
    if title:
        title = title.text
    else:
        print(soup)
        raise Exception('Error: Title not found')
    id_list = list()
    sticker_id_pattern = re.compile(r'stickershop/v1/sticker/(\d+)/\w+/sticker.png')
    sticker_list = soup.find_all('span', {'class': 'mdCMN09Image'})
    for sticker in sticker_list:
        match = sticker_id_pattern.search(sticker['style'])
        if match:
            id_list.append(match.group(1))
    id_list = list(set(id_list))
    return title, id_list, sticker_type
