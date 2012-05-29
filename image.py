# -*- coding: utf-8 -*-

from PIL import Image, ImageMath


def paste_composite(original, paste):
    """
    Вставляет в первое изображение второе, с учетом альфаканала обоих.
    Оба изображения должны быть в формате RGBA.
    """
    # Проблема в том, что PIL умеет тупо смешивать два изображения с заданным
    # альфаканалом. Это годится, когда мы накладываем полупрозрачную картинку
    # на непрозрачную — как раз нужно смешивать с альфаканалом той, которую
    # вставляют, результат будет полностью непрозрачным. В случае же, когда
    # смешиваются два полупрозрачных изображения, ни альфаканал, который нужно
    # использовать для смешивания, ни альфаканал получившегося изображения не
    # является альфаканалом первого или второго изображения. Оба эти канала
    # нужно вычислять.

    # im._new(im.getdata(3)) быстрее split()[-1].
    image_alpha = paste._new(paste.getdata(3))

    # alpha_chanel — альфаканал результирующего изображения. Будет вставлен
    # без зименений. im._new(im.getdata(3)) быстрее split()[-1].
    alpha_chanel = original._new(original.getdata(3))
    alpha_chanel.paste(Image.new('L', alpha_chanel.size, 255), image_alpha)

    # blending_chanel — альфаканал, который будет использован для смешивания
    # пикселей.
    blending_chanel = ImageMath.eval("convert(a * 255 / b, 'L')",
        a=image_alpha, b=alpha_chanel)
    del image_alpha

    original.paste(paste, (0, 0), blending_chanel)
    del blending_chanel

    original.putalpha(alpha_chanel)
    del alpha_chanel
