# -*- coding: utf-8 -*-

# Новое деление — это когда деление целых чисел дает не целое.
from __future__ import division

import re

from PIL import Image
from PIL.ImageColor import getrgb
from PIL.ImageFilter import (BLUR, CONTOUR, DETAIL,  # @UnusedImport
    EDGE_ENHANCE, EDGE_ENHANCE_MORE, EMBOSS, FIND_EDGES,  # @UnusedImport
    SMOOTH, SMOOTH_MORE, SHARPEN)  # @UnusedImport

from imagewallet.image import paste_composite, PALETTE_MODES
from imagewallet.filter_tools import size_handler


def _resize_more_or_less(more):
    def run(width, height, image_width, image_height):
        # Если соотношение сторон оргинального изображения более горизонтально
        # (ширина больше высоты), корректируем высоту в меньшую сторону.
        # Иначе ширину.
        if (width, height) == (None, None):
            # Теперь мы уверены, что хоть один параметр задан
            return image_width, image_height
        if height is None:
            master_width = True
        elif width is None:
            master_width = False
        else:
            master_width = image_width / image_height > width / height
            # Это XOR.
            master_width = more != master_width
        if master_width:
            height = round(width * image_height / image_width)
        else:
            width = round(height * image_width / image_height)
        return int(width), int(height)

    return run


def _square(width, height, image_width, image_height):
    if None in (width, height):
        raise ValueError('Square method does not support empty dimensions.')
    # Нужны размеры с запрошенной площадью и соотношением сторон оригинала.
    square = width * height
    ratio = image_width / image_height
    # ratio = width / height, width = ratio * height
    # square = ratio * height * height
    height = (square / ratio) ** .5
    width = ratio * height
    return int(round(width)), int(round(height))


def _exactly(width, height, image_width, image_height):
    if width is None:
        width = image_width
    if height is None:
        height = image_height
    return width, height


resize_methods = {
    'not_more': _resize_more_or_less(more=False),
    'not_less': _resize_more_or_less(more=True),
    'square': _square,
    'exactly': _exactly,
}


def resize(width=None, height=None, method='not_more', enlarge=False,
        resample=Image.ANTIALIAS):
    """
    Изменяет размеры изображения с помощью одного из четырех методов:
    not_more — пропорциональное изменение. Картинка будет максимально размера,
        при котором размеры не будут привышать заданные.
    not_less — пропорциональное изменение. Картинка будет минимального размера,
        при котором размеры будут больше заданных.
    square — пропорциональное изменение. Картинка будет иметь площадь заданного
        размера.
    exactly — непропорциональное приведение к заданным размерам.
    Любой из размеров width и height может быть не задан. Такое значение
    трактуется в зависимости от метода.
    По-умолчанию картинки только уменьшаются. Параметр enlarge разрешает
    увеличение картинки.
    Так же можно задать параметр resample, который передается в image.resize.
    """
    # Парсим параметры.
    width_handler = size_handler(width)
    height_handler = size_handler(height)
    resize_method = resize_methods[method]

    def run(image, format):
        # Уже распаршеные переменные преобразуем к физическим размерам.
        width = width_handler(image.size[0])
        height = height_handler(image.size[1])

        # Накладываем метод.
        width, height = resize_method(width, height, *image.size)

        # Следим, чтобы размер картинки не увеличился.
        if not enlarge:
            width = min(width, image.size[0])
            height = min(height, image.size[1])

        if (width, height) != image.size:
            image = image.resize((width, height), resample)
        return image

    return run


def crop(image, size, align=('50%', '50%')):
    if isinstance(size, basestring) and len(re.split(u'[×x*]', size)) == 2:
        size = re.split(u'[×x*]', size, maxsplit=1)
    elif isinstance(size, (tuple, list)) and len(size) == 2:
        size = list(size)
    else:
        raise TypeError('Size have unexpected type')

    if size[0] in (None, '', '?'):
        size[0] = image.size[0]
    if size[1] in (None, '', '?'):
        size[1] = image.size[1]

    size = map(int, size)

    offset = [0, 0]
    # фильтр не может увеличивать изображения
    for i in (0, 1):
        if size[i] >= image.size[i]:
            size[i] = image.size[i]
            continue
        try:
            int(align[i])
        except TypeError:
            # False или None
            offset[i] = size[0] - image.size[i]
        except ValueError:
            # с процентами
            a = float(align[i].rstrip('%'))
            offset[i] = int(round((size[i] - image.size[i]) * a / 100.0))
        else:
            # число
            offset[i] = int(align[i])

    if image.mode in PALETTE_MODES:
        bg = Image.new(image.mode, size, image.info.get('transparency'))
        bg.putpalette(image.getpalette())
    else:
        bg = Image.new(image.mode, size,
            image.info.get('_filter_background_color', (0, 0, 0, 0)))

    bg.paste(image, tuple(offset))
    bg.info = image.info
    image = bg
    return image


def padding():
    pass


def background(image, color):
    if not isinstance(color, tuple) or len(color) != 4 or color[3] != 0:
        if image.mode in PALETTE_MODES:
            if 'transparency' in image.info:
                if not isinstance(color, tuple):
                    color = getrgb(color)

                trans = image.info['transparency']
                del image.info['transparency']

                palette = image.getpalette()
                palette[trans * 3 + 0] = color[0]
                palette[trans * 3 + 1] = color[1]
                palette[trans * 3 + 2] = color[2]
                image.putpalette(palette)

        else:
            bg = Image.new(image.mode, image.size, color)
            bg.info = image.info

            if image.mode in ('RGBA', 'LA'):
                if isinstance(color, tuple) and len(color) == 4:
                    # semitransparent background
                    paste_composite(bg, image)
                else:
                    # solid background
                    bg = bg.convert(image.mode[:-1])
                    bg.paste(image.convert(image.mode[:-1]), (0, 0), image)
            else:
                bg.paste(image, (0, 0))
            image = bg

    image.info['_filter_background_color'] = color
    return image


def ambilight(image, size, scale=0.9, blur=5, crop=4):
    bg = image.resize((size[0] + crop * 2, size[1] + crop * 2), Image.ANTIALIAS)
    bg = filter(bg, BLUR, blur).crop((crop, crop, bg.size[0] - crop,
        bg.size[1] - crop))
    image.thumbnail(tuple([int(s * scale) for s in size]), Image.ANTIALIAS)
    bg.paste(image, tuple([int((size[i] - image.size[i]) / 2) for i in [0, 1]]))
    return bg


def convert(image, format):
    return image.convert(format)


def filter(image, filter, strength=1):
    while strength >= 1:
        image = image.filter(filter)
        strength -= 1
    if strength == 0:
        return image
    else:
        return Image.blend(image, image.filter(filter), strength)


def colorize(image, color='#fff', alpha=0.5):
    return Image.blend(image, Image.new(image.mode, image.size, color), alpha)


def minimize(image):
    return image


def quality(image, quality):
    image.info['quality'] = quality
    return image


def progressive(image):
    image.info['progressive'] = True
    return image


def optimize(image):
    image.info['optimize'] = True
    return image
