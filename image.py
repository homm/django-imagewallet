# -*- coding: utf-8 -*-

from PIL import Image, ImageMath

PALETTE_MODES = ('P',)


def paste_composite(original, paste):
    # this faster then split()[-1]
    image_alpha = paste._new(paste.getdata(3))

    # this faster then split()[-1]
    alpha_chanel = original._new(original.getdata(3))
    alpha_chanel.paste(Image.new('L', alpha_chanel.size, 255), image_alpha)

    blending_chanel = ImageMath.eval("convert(a * 255 / b, 'L')",
        a=image_alpha, b=alpha_chanel)

    original.paste(paste, (0, 0), blending_chanel)
    original.putalpha(alpha_chanel)
    del image_alpha, alpha_chanel, blending_chanel
