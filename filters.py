# -*- coding: utf-8 -*-

# Новое деление — это когда деление целых чисел дает не целое.
from __future__ import division

from PIL import Image, ImageColor
from PIL.ImageFilter import (BLUR, CONTOUR, DETAIL,  # @UnusedImport
    EDGE_ENHANCE, EDGE_ENHANCE_MORE, EMBOSS, FIND_EDGES,  # @UnusedImport
    SMOOTH, SMOOTH_MORE, SHARPEN)  # @UnusedImport

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
    # ratio = width / height => width = ratio * height
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
    resize_method = method if callable(method) else resize_methods[method]

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


def crop(width=None, height=None, halign='50%', valign='50%', background=None):
    """
    Задает изображению нужные размеры. Может использоваться как для обрезания,
    так и для задания полей. Преметры width и height задают размеры. Любой из
    них может быть не укзан, тогда данный рахмер изменене не будет. Пераметры
    halign и valign задают расположение исходного изображения в новом. Если
    размеры увеличиваются и режим изображения не поддерживает прозрачность,
    пустое место заливается цветом background. Если этот цвет не задан, берется
    цвет background у формата.
    """
    # Парсим параметры.
    width_handler = size_handler(width)
    height_handler = size_handler(height)
    halign_handler = size_handler(halign)
    valign_handler = size_handler(valign)

    def run(image, format):
        # Уже распаршеные переменные преобразуем к физическим размерам.
        # None становится текущим размером.
        size = (width_handler(image.size[0]) or image.size[0],
            height_handler(image.size[1]) or image.size[1])

        # Для прозрачных не нужно указывать фон.
        if image.mode in ['RGBA', 'LA']:
            new = Image.new(image.mode, size)
        elif image.mode == 'P' and 'transparency' in image.info:
            new = Image.new(image.mode, size, image.info['transparency'])
            new.putpalette(image.getpalette())
        else:
            if background is None:
                new = Image.new(image.mode, size, format.background)
            else:
                new = Image.new(image.mode, size, background)

        box = (halign_handler(size[0] - image.size[0]),
            valign_handler(size[1] - image.size[1]))
        new.paste(image, box)
        new.info = image.info.copy()
        return new

    return run


def convert(mode='RGB', background='white', data=None, dither=None,
        palette=Image.WEB, colors=256):
    """
    Преобразует изображение в заданный режим. Если необходимо, заливает фон.
    """
    background = ImageColor.getrgb(background)

    def run(image, format):
        # Преобразования не требуется
        if mode is None or mode == image.mode:
            return image

        # Если режим, к которому нужно преобразовать, не поддерживает
        # прозрачность, а исходное изображение в одном из режимов,
        # поддерживающих, нужны подложить под прозрачные пиксели фон.
        # Причем, режим с палитрой считается неподдерживающим прозрачность,
        # потому что адекватно преобразовать в него альфаканал все равно не
        # получится.
        if mode not in ('RGBA', 'LA'):
            # Черно-белые с альфаканалом преобразуем в RGBA. Можно было бы
            # заморочиться с извлечением L и А и передачей их в paste отдельно,
            # что сократило бы потребление памяти.
            if image.mode == 'LA':
                # Конвертируем без опций, для RGBA они не применимы.
                image = image.convert('RGBA')

            # Тут нет else. Предыдущий случай тоже обрабатывается здесь.
            if image.mode == 'RGBA':
                # Картинка - подложка, состоящая из залитого фона.
                bg = Image.new('RGB', image.size, background)
                # Вставляем изображение. paste вставляет пикселы первого
                # аргумента с помошью альфаканала третьего.
                # Альфаканал первого игнорируется.
                bg.paste(image, None, image)
                # Теперь bg и есть искомое изображение.
                image = bg

            # Палитру не нужно смешивать, достаточно заменить цвет, указанный
            # как прозрачный на цвет фона.
            elif image.mode == 'P' and 'transparency' in image.info:
                # Будем менять палитру, картинку портить нельзя.
                image = image.copy()
                image_palette = image.getpalette()
                # Тут предполагается, что палитра в формате RGB.
                offset = image.info['transparency'] * 3
                image_palette[offset:offset + 3] = background
                # Кладем на место.
                image.putpalette(image_palette)

        # С палитрой бида. Если преобразовывать из нее в формат, поддерживающий
        # прозрачность, прозрачный цвет палитры становится непрозрачным.
        elif image.mode == 'P' and 'transparency' in image.info:
            # Из прозрачного цвета нужно получить маску.
            mask = image.convert('L').point(lambda i:
                0 if i == image.info['transparency'] else 255)
            # Конвертируем без опций, для RGBA они не применимы.
            image = image.convert('RGBA')
            image.putalpha(mask)

        # Теперь можно конвертировать.
        return image.convert(mode, data, dither, palette, colors)

    return run
