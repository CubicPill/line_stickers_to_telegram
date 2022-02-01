from enum import Enum


class StickerType(Enum):
    STATIC_STICKER = 'static'
    ANIMATED_STICKER = 'animated'
    POPUP_STICKER = 'popup'
    STATIC_WITH_SOUND_STICKER = 'static&sound'
    ANIMATED_AND_SOUND_STICKER = 'animated&sound'
    POPUP_AND_SOUND_STICKER = 'popup&sound'
    SOUND = 'sound'
    MAIN_ANIMATION='main_animation'


class StickerSetSource(Enum):
    LINE = 'line',
    YABE = 'yabe'


SET_URL_TEMPLATES = {
    StickerSetSource.LINE: 'https://store.line.me/stickershop/product/{id}/{lang}?from=sticker',
    StickerSetSource.YABE: 'https://yabeline.tw/Stickers_Data.php?Number={id}'
}

STICKER_URL_TEMPLATES = {
    StickerType.SOUND: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_sound.m4a',
    StickerType.STATIC_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/iPhone/sticker@2x.png',
    StickerType.STATIC_WITH_SOUND_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/android/sticker@2x.png',
    StickerType.ANIMATED_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_animation@2x.png',
    StickerType.MAIN_ANIMATION:'https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/IOS/main_animation.png',
    StickerType.ANIMATED_AND_SOUND_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_animation@2x.png',
    StickerType.POPUP_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_popup@2x.png',
    StickerType.POPUP_AND_SOUND_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_popup@2x.png'
}
FAKE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36'
}
