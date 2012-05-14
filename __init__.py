# -*- coding: utf-8 -*-

from PIL.ImageFilter import (BLUR, CONTOUR, DETAIL, EDGE_ENHANCE,
    EDGE_ENHANCE_MORE, EMBOSS, FIND_EDGES, SMOOTH, SMOOTH_MORE, SHARPEN)
from imagewallet.wallet import Wallet, ImageFormat, ORIGINAL_FORMAT
from imagewallet.fields import WalletField


def Filter(filter, *args, **kwargs):
    from imagewallet import filters
    from django.utils.encoding import force_unicode

    if callable(filter):
        pass
    elif callable(getattr(filters, filter, False)):
        filter = getattr(filters, filter)
    else:
        raise ValueError("Filter %s not found." % force_unicode(filter))

    if isinstance(filter, type):
        return filter(*args, **kwargs)
    else:
        def run(*moreargs, **morekwargs):
            return filter(*(moreargs + args), **dict(morekwargs, **kwargs))
        return run
