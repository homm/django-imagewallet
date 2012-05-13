# -*- coding: utf-8 -*-

from os import path as os_path

from django.utils.encoding import force_unicode
from django.utils.functional import curry
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files import File
from django.core.files.images import get_image_dimensions

import PIL


ORIGINAL_FORMAT = 'original'
# max block size for jpeg save in PIL
MAXBLOCK = 3200 * 2000


class Wallet(object):
    # this type used when image can be loaded, but it's type not supported
    image_type_fallback = 'PNG'
    image_types_extensions = {
        'PNG':  'png',
        'JPEG': 'jpg',
    }
    # Original Image, stored after saving or loaded from disk
    _loaded_original = False

    def __init__(self, formats, pattern=None, original_image_type=None,
            storage=None):
        """
        Pattern is a string with 2 replaces: "size" and "extension".
        original_image_type is type of saved original image.
        """
        self.formats = formats
        self._pattern = pattern
        self.original_image_type = original_image_type
        self.storage = storage or default_storage

        if original_image_type is not None and not pattern:
            raise ValueError('For saved files pattern is required')

        if pattern and '%(size)s' not in pattern:
            raise ValueError('Pattern string should contain %%(size)s replace.',
                ' Given pattern: %s' % pattern)

    def __unicode__(self):
        if self:
            return u'%s;%s' % (self._pattern, self.original_image_type)
        else:
            return u''

    def set_pattern(self, value):
        if self:
            raise ValueError("Can not change pattern for saved wallet. Delete first.")
        self._pattern = value
    pattern = property(lambda self: self._pattern, set_pattern)

    def __nonzero__(self):
        """
        original_image_type can be only for saved images. If original_image_type
        is None, nothing saved in this wallet.
        """
        return self.original_image_type is not None

    def __reduce__(self):
        """
        Save wallet as string.
        """
        return (unicode, (self.__unicode__(),))

    @classmethod
    def populate_formats(cls, formats):
        cls = Wallet
        for format in formats:
            url_name = 'url_%s' % format
            if not hasattr(cls, url_name):
                setattr(cls, url_name, property(curry(cls.get_url, format=format)))
            path_name = 'path_%s' % format
            if not hasattr(cls, path_name):
                setattr(cls, path_name, property(curry(cls.get_path, format=format)))
            size_name = 'size_%s' % format
            if not hasattr(cls, size_name):
                setattr(cls, size_name, property(curry(cls.get_size, format=format)))

    def load_original(self):
        if not self:
            return None
        if not self._loaded_original:
            image = self.storage.open(self.get_path(ORIGINAL_FORMAT))
            self._loaded_original = PIL.Image.open(image)
        return self._loaded_original

    def save(self, image):
        """
        Loads new image to wallet.
        image may be path to file, django file or pil image
        Returns original image.
        """
        if self:
            raise ValueError("Can not save another images in saved wallet. Delete first.")

        if not self._pattern:
            raise ValueError("Pattern should be present.")

        if '%(size)s' not in self._pattern:
            raise ValueError('Pattern string should contain %%(size)s replace. Given pattern: %s' % self._pattern)

        if isinstance(image, basestring):
            image = self.storage.open(image)
            image = PIL.Image.open(image)
        elif isinstance(image, (file, File)):
            image = PIL.Image.open(image)
        elif isinstance(image, PIL.Image.Image):
            pass
        else:
            raise ValueError("Argument of this type is not supported.")

        self._loaded_original = image

        self.original_image_type = self.get_image_type(ORIGINAL_FORMAT,
            self._loaded_original.format)

        # process original image
        self._loaded_original = self.process_format(ORIGINAL_FORMAT, save=True)

        return self._loaded_original

    def process_format(self, format, image=None, save=False):
        """
        Process image, make one thumb from given format 
        """
        if image is None:
            image = self.load_original()

        if not image:
            return image

        for filter in self.formats[format]:
            if callable(filter):
                image = filter(image)

        if save:
            save_params = image.info

            # Save empty file to ensure path is exists
            self.storage.save(self.get_path(format), ContentFile(''))
            file = self.storage.open(self.get_path(format), mode='wb')
            try:
                image_type = self.get_image_type(format)
                if image_type == 'JPEG' and image.mode not in PIL.JpegImagePlugin.RAWMODE:
                    image = image.convert('RGB')

                try:
                    # Try save image with big block size
                    OLD_MAXBLOCK = PIL.ImageFile.MAXBLOCK
                    PIL.ImageFile.MAXBLOCK = MAXBLOCK
                    image.save(file, format=image_type, **save_params)
                except IOError:
                    # Else remove all options affected expected block size
                    if 'optimize' in save_params:
                        del save_params['optimize']
                    if 'progression' in save_params:
                        del save_params['progression']
                    if 'progressive' in save_params:
                        del save_params['progressive']
                    image.save(file, format=image_type, **save_params)
                finally:
                    PIL.ImageFile.MAXBLOCK = OLD_MAXBLOCK

            finally:
                file.close()
        return image

    def process_all_formats(self):
        for format in self.formats:
            if format != ORIGINAL_FORMAT:
                self.process_format(format, save=True)

    def copy(self, wallet):
        """
        Copy image from other wallet to this without changing. Filters for original format ignored.
        """
        if self:
            raise ValueError("Can not save another images in saved wallet. Delete first.")
        if not wallet:
            return
        self.original_image_type = wallet.original_image_type
        _from = wallet.get_path(ORIGINAL_FORMAT)
        _to = self.get_path(ORIGINAL_FORMAT)
        self.storage.save(_to, wallet.storage.open(_from))

    def delete(self):
        """
        Mark wallet as not saved and delete all files
        """
        if not self:
            return
        for format in self.formats:
            path = self.get_path(format)
            self.storage.delete(path)
        self.original_image_type = None
        self._loaded_original = False

    def clean(self, format):
        """
        Delete not-original images from disk. Safe for original image.
        """
        if not self or format == ORIGINAL_FORMAT:
            # Use delete() instead.
            return
        path = self.get_path(format)
        self.storage.delete(path)

    def get_size(self, format, image=None):
        " TODO: cache this"
        if not self:
            return (None, None)
        path = self.get_path(format)
        if format != ORIGINAL_FORMAT and not self.storage.exists(path):
            image = self.process_format(format, save=True)
            return image.size
        else:
            return get_image_dimensions(self.storage.open(path))

    def get_url(self, format):
        # url returns only for existing images
        if self:
            path = self.get_path(format)
            # if image not found, it created
            if format != ORIGINAL_FORMAT and not self.storage.exists(path):
                self.process_format(format, save=True)
            return self.storage.url(path)
        else:
            return None

    def get_path(self, format):
        if not self._pattern:
            return None
        image_type = self.get_image_type(format)
        extension = self.image_types_extensions.get(image_type)
        return self._pattern % {'size': format, 'extension': extension}

    def get_image_type(self, format, original_image_type=None):
        if format not in self.formats:
            raise AttributeError("%s has no format %s" %
                (self.__class__.__name__, format))

        # for not original format returns user-defined type
        if format != ORIGINAL_FORMAT and isinstance(self.formats[format][-1], basestring):
            return self.formats[format][-1]

        # for saved wallets return original image type
        if self.original_image_type is not None:
            return self.original_image_type

        # if don't saved, return custom image type for original format
        if isinstance(self.formats[ORIGINAL_FORMAT][-1], basestring):
            return self.formats[ORIGINAL_FORMAT][-1]

        if original_image_type in self.image_types_extensions:
            return original_image_type

        # for unsupported types it will be png
        return self.image_type_fallback


def reverse_curry(_curried_func, *moreargs, **morekwargs):
    def _curried(*args, **kwargs):
        return _curried_func(*(args + moreargs), **dict(kwargs, **morekwargs))
    return _curried

from imagewallet import filters


def Filter(filter, *args, **kwargs):
    if callable(filter):
        pass
    elif callable(getattr(filters, filter, False)):
        filter = getattr(filters, filter)
    else:
        raise ValueError("Filter %s not found." % force_unicode(filter))

    if isinstance(filter, type):
        return filter(*args, **kwargs)
    else:
        return reverse_curry(filter, *args, **kwargs)

