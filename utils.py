import re
from enum import Enum
from threading import Lock


class PackNotFoundException(Exception):
    pass


class StickerType(Enum):
    STATIC_STICKER = "STATIC"
    ANIMATED_STICKER = "ANIMATION"
    POPUP_STICKER = "POPUP"
    STATIC_WITH_SOUND_STICKER = "SOUND"
    ANIMATED_AND_SOUND_STICKER = "ANIMATION_SOUND"
    POPUP_AND_SOUND_STICKER = "POPUP_SOUND"
    MESSAGE_STICKER = "PER_STICKER_TEXT"  # message stickers
    CUSTOM_STICKER = "NAME_TEXT"  # custom stickers
    # below are not exact value in metadata but used for convenience
    ANIMATED_EMOJI = "ANIMATION_STICON"  # animated emoji
    EMOJI = "STICON"  # emoji
    # SOUND = '_sound'  # sound file only
    # MAIN_ANIMATION = '_main_animation'
    # MAIN_POPUP = '_main_popup'


# match the pack id (int for sticker and hex for emoji)
PACK_ID_REGEX = re.compile(r"/([a-f0-9]+)/")


# sticker set webpage
class SourceUrlType(Enum):
    LINE = "line"
    LINE_EMOJI = "line_emoji"
    YABE = "yabe"
    YABE_EMOJI = "yabe_emoji"


def sticker_type_properties(sticker_type: StickerType):
    has_animation = False
    has_sound = False
    has_popup = False
    has_text_overlay = False
    is_emoji = False
    if sticker_type in [
        StickerType.ANIMATED_STICKER,
        StickerType.POPUP_STICKER,
        StickerType.ANIMATED_AND_SOUND_STICKER,
        StickerType.POPUP_AND_SOUND_STICKER,
        StickerType.ANIMATED_EMOJI,
    ]:
        has_animation = True
    if sticker_type in [
        StickerType.STATIC_WITH_SOUND_STICKER,
        StickerType.ANIMATED_AND_SOUND_STICKER,
        StickerType.POPUP_AND_SOUND_STICKER,
    ]:
        has_sound = True
    if sticker_type in [StickerType.POPUP_STICKER, StickerType.POPUP_AND_SOUND_STICKER]:
        # for popup sticker, different sources should be used for static and animation
        has_popup = True
    if sticker_type in [StickerType.MESSAGE_STICKER]:
        # CUSTOM_STICKER also could have message overlay, but it's not supported yet without logging to line
        has_text_overlay = True
    if sticker_type in [StickerType.ANIMATED_EMOJI, StickerType.EMOJI]:
        is_emoji = True
    return has_animation, has_sound, has_popup, has_text_overlay, is_emoji


STICKER_SET_URL_REGEX = {
    SourceUrlType.LINE: (
        re.compile(r"https://store.line.me/stickershop/product/(\d+)/?(\w+)?"),
        False,
    ),
    SourceUrlType.LINE_EMOJI: (
        re.compile(r"https://store.line.me/emojishop/product/([a-f0-9]+)/?(\w+)?"),
        True,
    ),
    SourceUrlType.YABE: (
        re.compile(r"https://yabeline.tw/Stickers_Data.php\?Number=(\d+)"),
        False,
    ),
    SourceUrlType.YABE_EMOJI: (
        re.compile(r"https://yabeline.tw/Emoji_Data.php\?Number=(\d+)"),
        True,
    ),
}
STICKER_SET_URL_TEMPLATES = {
    SourceUrlType.LINE: "https://store.line.me/stickershop/product/{pack_id}/{lang}?from=sticker",
    SourceUrlType.LINE_EMOJI: "https://store.line.me/emojishop/product/{pack_id}/{lang}",
    SourceUrlType.YABE: "https://yabeline.tw/Stickers_Data.php?Number={pack_id}",
    SourceUrlType.YABE_EMOJI: "https://yabeline.tw/Emoji_Data.php?Number={pack_id}",
}
# metadata
STICKER_SET_META_URL = "https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/iphone/productInfo.meta"
EMOJI_SET_META_URL = (
    "https://stickershop.line-scdn.net/sticonshop/v1/{pack_id}/sticon/iphone/meta.json"
)
# sticker zip archive
STICKER_ZIP = "https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/iphone/stickerpack@2x.zip"
EMOJI_ZIP = "https://stickershop.line-scdn.net/sticonshop/v1/{pack_id}/sticon/iphone/package.zip"
EMOJI_ANIMATION_ZIP = "https://stickershop.line-scdn.net/sticonshop/v1/{pack_id}/sticon/iphone/package_animation.zip"

STICKER_ZIP_TEMPLATES = {
    StickerType.STATIC_STICKER: "https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/iphone/stickers@2x.zip",
    StickerType.ANIMATED_STICKER: "https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/iphone/stickerpack@2x.zip",
    StickerType.POPUP_STICKER: "https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/iphone/stickerpack@2x.zip",
    StickerType.STATIC_WITH_SOUND_STICKER: "https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/iphone/stickerpack@2x.zip",
    StickerType.ANIMATED_AND_SOUND_STICKER: "https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/iphone/stickerpack@2x.zip",
    StickerType.POPUP_AND_SOUND_STICKER: "https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/iphone/stickerpack@2x.zip",
    StickerType.MESSAGE_STICKER: "https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/iphone/sticker_custom_plus_base@2x.zip",
    StickerType.CUSTOM_STICKER: "https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/iphone/sticker_name_base@2x.zip",
    StickerType.ANIMATED_EMOJI: "https://stickershop.line-scdn.net/sticonshop/v1/{pack_id}/sticon/iphone/package_animation.zip",
    StickerType.EMOJI: "https://stickershop.line-scdn.net/sticonshop/v1/{pack_id}/sticon/iphone/package.zip",
}
# default overlay text for message sticker
MESSAGE_STICKER_OVERLAY_TEXT = "https://store.line.me/overlay/sticker/{pack_id}/{sticker_id}/iPhone/sticker.png?text={text}&timestamp={ts}"
MESSAGE_STICKER_OVERLAY_DEFAULT = "https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/sticker/{sticker_id}/iPhone/overlay/plus/default/sticker@2x.png"
# NAME_TEXT_STICKER_OVERLAY_TEXT = 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{pack_id}/iPhone/overlay/name/{id}/sticker@2x.png'
# 'https://store.line.me/api/custom-sticker/preview/{pack_id}/zh-Hant?text={text}&_={ts}'
# requires login to line

# individual sticker
STICKER_URL_TEMPLATES = {
    # StickerType.SOUND: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/IOS/sticker_sound.m4a',
    StickerType.STATIC_STICKER: "https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/iPhone/sticker@2x.png",
    StickerType.STATIC_WITH_SOUND_STICKER: "https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/android/sticker@2x.png",
    StickerType.ANIMATED_STICKER: "https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/IOS/sticker_animation@2x.png",
    # StickerType.MAIN_ANIMATION: 'https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/IOS/main_animation.png',
    StickerType.ANIMATED_AND_SOUND_STICKER: "https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/IOS/sticker_animation@2x.png",
    StickerType.POPUP_STICKER: "https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/IOS/sticker_popup.png",
    StickerType.POPUP_AND_SOUND_STICKER: "https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/IOS/sticker_popup.png",
    # StickerType.MAIN_POPUP: 'https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/IOS/main_popup.png',
    StickerType.ANIMATED_EMOJI: "https://stickershop.line-scdn.net/sticonshop/v1/sticon/{pack_id}/iPhone/{sticker_id}_animation.png",
    StickerType.EMOJI: "https://stickershop.line-scdn.net/sticonshop/v1/sticon/{pack_id}/iPhone/{sticker_id}.png",
}
# request headers
FAKE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36"
}
_counter_lock = Lock()
_task_completed_counter = 0


def get_counter_value():
    with _counter_lock:
        return _task_completed_counter


def increase_counter():
    with _counter_lock:
        global _task_completed_counter
        _task_completed_counter += 1


def reset_counter():
    with _counter_lock:
        global _task_completed_counter
        _task_completed_counter = 0
