# -*- coding: utf-8 -*-

from PIL import Image, ImageFilter

PALETTE_MODES = ('P',)

def alpha_composite(image, background):
    
    image.load()
    background.load()
    
    # mask for image
    alpha = image.split()[-1]
    
    # mask from background
    background_alpha = background.split()[-1]
    
    alpha_data = alpha.getdata()
    background_alpha_data = background_alpha.getdata()
    
    new_blending = list(alpha.getdata())
    new_alpha = list(background_alpha.getdata())
    
    for i in xrange(len(alpha_data)):
        alpha_pixel = new_blending[i]
        background_alpha_pixel = new_alpha[i]
        if alpha_pixel == 0:
            new_blending[i] = 0
            #new_alpha[i] = background_alpha_pixel
        elif alpha_pixel == 255:
            new_alpha[i] = 255
            new_blending[i] = 255
        else:
            new_alpha[i] = alpha_pixel + (255 - alpha_pixel) * background_alpha_pixel / 255
            new_blending[i] = alpha_pixel * 255 / new_alpha[i]
    
    del alpha_data
    del background_alpha_data
    
    alpha.putdata(new_alpha)
    background_alpha.putdata(new_blending)
    
    background.paste(image, (0, 0), background_alpha)
    
    background.putalpha(alpha)
    
    return background