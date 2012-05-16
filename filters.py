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


def _not_more(width, height, image_width, image_height):
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
    if master_width:
        height = round(width * image_height / image_width)
    else:
        width = round(height * image_width / image_height)
    return int(width), int(height)


def _not_less(width, height, image_width, image_height):
    # Если соотношение сторон оргинального изображения более горизонтально
    # (ширина больше высоты), корректируем ширину в большую сторону.
    # Иначе высоту.
    if (width, height) == (None, None):
        # Теперь мы уверены, что хоть один параметр задан
        return image_width, image_height
    if height is None:
        master_width = True
    elif width is None:
        master_width = False
    else:
        master_width = image_width / image_height < width / height
    if master_width:
        height = round(width * image_height / image_width)
    else:
        width = round(height * image_width / image_height)
    return int(width), int(height)


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
    'not_more': _not_more,
    'not_less': _not_less,
    'square': _square,
    'exactly': _exactly,
}


def new_resize(width=None, height=None, method='not_more', enlarge=False,
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
    Любой из размеров width и height может быть не задан, что трактуется как
    текущий размер у картинки.
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


" Size method. Result image will be not more then given size"
NOT_MORE = 'not_more'
" Size method. Result image will be not less then given size"
NOT_LESS = 'not_less'
" Size method. Result image will be exact given size. Aspect ratio is not taken into account."
EXACTLY = 'exactly'
" Size method. Image size will be mean of NOT_MORE and NOT_LESS methods."
MEDIAN = 'median'


class Resize(object):
    @classmethod
    def method_not_more(cls, original_width, original_height, requested_width, requested_height):
        master = None

        if not requested_width:
            master = 'height'
        if not requested_height:
            master = 'width'

        if not master:
            master = 'width' if (original_width / float(requested_width)) > (original_height / float(requested_height)) else 'height'

        if master == 'width':
            requested_height = original_height * requested_width / float(original_width)
        else:
            requested_width = original_width * requested_height / float(original_height)

        return int(requested_width), int(requested_height)

    @classmethod
    def method_not_less(cls, original_width, original_height, requested_width, requested_height):
        master = None

        if not requested_width:
            master = 'height'
        if not requested_height:
            master = 'width'

        if not master:
            master = 'width' if (original_width / float(requested_width)) < (original_height / float(requested_height)) else 'height'

        if master == 'width':
            requested_height = original_height * requested_width / float(original_width)
        else:
            requested_width = original_width * requested_height / float(original_height)

        return int(requested_width), int(requested_height)

    @classmethod
    def method_exactly(cls, original_width, original_height, requested_width, requested_height):
        if not requested_width:
            requested_width = original_width
        if not requested_height:
            requested_height = original_height
        return requested_width, requested_height

    @classmethod
    def method_median(cls, original_width, original_height, requested_width, requested_height):
        min_width, min_height = cls.method_not_more(original_width, original_height, requested_width, requested_height)
        max_width, max_height = cls.method_not_less(original_width, original_height, requested_width, requested_height)
        return int((min_width + max_width) / 2), int((min_height + max_height) / 2)

    METHOD_FUNCTIONS = {
        NOT_MORE: 'method_not_more',
        NOT_LESS: 'method_not_less',
        EXACTLY: 'method_exactly',
        MEDIAN: 'method_median',
    }

    def __init__(self, size, method=NOT_MORE, enlarge=False, strict_size=(False, False), align=('50%', '50%')):
        """
        Convert one file to another according given options.
        Size can be one of following types:
            tuple (10, 20)
            string "10×20" "10x20" "10*20"
        Any dimension can be 0 or None, what is same.
        strict_size can be boolean or tuple of two booleans.
        First member is strict size of width, second of height
        """
        self.size, self.method, self.enlarge, self.strict_size = self._parse_params(size, method, enlarge, strict_size)
        if not isinstance(align, (tuple, list)):
            align = (align, align)
        self.align = align

    def _parse_params(self, size, method, enlarge, strict_size):
        if isinstance(size, basestring) and len(re.split(u'[×x*]', size)) == 2:
            size = re.split(u'[×x*]', size, maxsplit=1)
        elif isinstance(size, (tuple, list)) and len(size) == 2:
            size = list(size)
        else:
            raise TypeError('Size have unexpected type')

        if not isinstance(strict_size, (tuple, list)):
            strict_size = (strict_size, strict_size)

        if size[0] in (None, '', '?'):
            size[0] = 0
        if size[1] in (None, '', '?'):
            size[1] = 0

        size = map(int, size)

        if method in self.METHOD_FUNCTIONS:
            method = getattr(self, self.METHOD_FUNCTIONS[method])
        elif callable(method):
            pass
        else:
            raise TypeError('Method should be callable or constant')

        return size, method, enlarge, strict_size

    def __call__(self, image):
        if not any(self.size):
            """ if size not specified, no need do anything """
            return image

        requested_width, requested_height = self.size

        new_width, new_height = self.method(image.size[0], image.size[1],
            self.size[0], self.size[1])

        if not self.enlarge:
            if new_width > image.size[0]:
                new_width = image.size[0]
            if new_height > image.size[1]:
                new_height = image.size[1]

        if new_width != image.size[0] or new_height != image.size[1]:
            image = image.resize((new_width, new_height), Image.ANTIALIAS)

        if not requested_width:
            requested_width = new_width
        if not requested_height:
            requested_height = new_height

        if (self.strict_size[0] and new_width != requested_width) or (self.strict_size[1] and new_height != requested_height):
            offset_x = 0
            if self.strict_size[0]:
                if self.align[0] is False:
                    offset_x = requested_width - new_width
                else:
                    try:
                        offset_x = int(self.align[0])
                        if offset_x < 0:
                            offset_x = requested_width - new_width + offset_x
                    except:
                        if type(self.align[0]) is str and self.align[0].rstrip('%').isdigit():
                            offset_x = int(round((requested_width - new_width) * float(self.align[0].rstrip('%')) / 100.0))
                        else:
                            raise TypeError('align format not supported')
                new_width = requested_width

            offset_y = 0
            if self.strict_size[1]:
                if self.align[1] is False:
                    offset_y = requested_height - new_height
                else:
                    try:
                        offset_y = int(self.align[1])
                        if offset_y < 0:
                            offset_y = requested_height - new_height + offset_y
                    except:
                        if type(self.align[1]) is str and self.align[1].rstrip('%').isdigit():
                            offset_y = int(round((requested_height - new_height) * float(self.align[1].rstrip('%')) / 100.0))
                        else:
                            raise TypeError('align format not supported')
                new_height = requested_height

            if image.mode in PALETTE_MODES:
                bg = Image.new(image.mode, (new_width, new_height),
                    image.info.get('transparency'))
                bg.putpalette(image.getpalette())
            else:
                bg = Image.new(image.mode, (new_width, new_height),
                    image.info.get('_filter_background_color', (0, 0, 0, 0)))
            bg.paste(image, (offset_x, offset_y))
            bg.info = image.info
            image = bg

        return image

resize = Resize


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
