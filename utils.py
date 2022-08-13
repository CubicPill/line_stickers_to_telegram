from enum import Enum


class StickerType(Enum):
    STATIC_STICKER = 'static'
    ANIMATED_STICKER = 'animated'
    POPUP_STICKER = 'popup'
    STATIC_WITH_SOUND_STICKER = 'static&sound'
    ANIMATED_AND_SOUND_STICKER = 'animated&sound'
    POPUP_AND_SOUND_STICKER = 'popup&sound'
    SOUND = 'sound'
    ANIMATED_STICON = 'animated_sticon'  # animated emoji
    STICON = 'sticon'  # emoji
    MAIN_ANIMATION = 'main_animation'
    MAIN_POPUP = 'main_popup'


class StickerSetSource(Enum):
    LINE = 'line'
    LINE_EMOJI = 'line_emoji'
    YABE = 'yabe'
    YABE_EMOJI = 'yabe_emoji'


SET_URL_TEMPLATES = {
    StickerSetSource.LINE: 'https://store.line.me/stickershop/product/{id}/{lang}?from=sticker',
    StickerSetSource.LINE_EMOJI: 'https://store.line.me/emojishop/product/{id}/{lang}',
    StickerSetSource.YABE: 'https://yabeline.tw/Stickers_Data.php?Number={id}',
    StickerSetSource.YABE_EMOJI: 'https://yabeline.tw/Emoji_Data.php?Number={id}'
}

STICKER_URL_TEMPLATES = {
    StickerType.SOUND: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_sound.m4a',
    StickerType.STATIC_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/iPhone/sticker@2x.png',
    StickerType.STATIC_WITH_SOUND_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/android/sticker@2x.png',
    StickerType.ANIMATED_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_animation@2x.png',
    StickerType.MAIN_ANIMATION: 'https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/IOS/main_animation.png',
    StickerType.ANIMATED_AND_SOUND_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_animation@2x.png',
    StickerType.POPUP_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_popup.png',
    StickerType.POPUP_AND_SOUND_STICKER: 'https://stickershop.line-scdn.net/stickershop/v1/sticker/{id}/IOS/sticker_popup.png',
    StickerType.MAIN_POPUP: 'https://stickershop.line-scdn.net/stickershop/v1/product/{pack_id}/IOS/main_popup.png',
    StickerType.ANIMATED_STICON: 'https://stickershop.line-scdn.net/sticonshop/v1/sticon/{pack_id}/iPhone/{id}_animation.png',
    StickerType.STICON: 'https://stickershop.line-scdn.net/sticonshop/v1/sticon/{pack_id}/iPhone/{id}.png'
}
FAKE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/63.0.3239.132 Safari/537.36'
}
