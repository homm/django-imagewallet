# -*- coding: utf-8 -*-

from exceptions import IncorrectLoaded

from django.utils.encoding import force_unicode
from django.utils.functional import curry
from django.core.files.base import ContentFile, StringIO
from django.core.files.storage import default_storage
from django.core.files import File
from django.core.files.images import get_image_dimensions

from PIL import Image

from os import path as os_path

import ImageFile
ImageFile.MAXBLOCK = 1000000 # fix problem with large images and optimized files

ORIGINAL_FORMAT = 'original'

class Wallet(object):
    # used for files in supported for load formats and don't supported for save (bmp, tiff, etc.)
    image_type_fallback = 'PNG'
    image_types_extensions = {
        'PNG':  'png',
        'JPEG': 'jpg',
        'GIF':  'gif',
    }
    # Original Image, stored after saving or loaded from disk
    _loaded_original = False
    
    def __init__(self, formats, pattern, original_image_type=False, storage=None):
        """
        Pattern is a string with 2 replaces: "size" and "extension".
        original_image_type is type of saved original image.
        """
        
        if not ('%(size)' in pattern and '%(extension)' in pattern):
            raise IncorrectLoaded('Pattern string must be string with %%(size) and %%(extension) replaces. Given pattern: %s' % pattern)
        
        self.formats = formats
        self._pattern = pattern
        self.original_image_type = original_image_type
        self.storage = storage or default_storage
    
    @property
    def pattern(self):
        if callable(self._pattern):
            self._pattern = self._pattern()
        return self._pattern
    
    def __unicode__(self):
        if self:
            return u'%s;%s' % (self.pattern, self.original_image_type)
        else:
            return u''
    
    def __nonzero__(self):
        """
        original_image_type can be only for saved images. If original_image_type is False, nothing saved in this wallet.
        """
        return not self.original_image_type is False
    
    def __reduce__(self):
        """
        Save wallet as string. 
        """
        return (unicode, (self.__unicode__(),))
    
    @classmethod
    def populate_formats(cls, formats):
        for format in formats:
            url_name = 'url_%s' % format
            if not hasattr(cls, url_name):
                setattr(cls, url_name, curry(cls.get_url, format=format))
            path_name = 'path_%s' % format
            if not hasattr(cls, path_name):
                setattr(cls, path_name, curry(cls.get_path, format=format))
            size_name = 'size_%s' % format
            if not hasattr(cls, size_name):
                setattr(cls, size_name, curry(cls.get_size, format=format))
 
    def save(self, image, image_type=None, generate=False):
        """
        Loads new image to wallet.
        image may be path to file, file object, django object or pil image
        generate may be True, False, or None
        Returns original image.
        """
        if isinstance(image, basestring):
            image = self.storage.open(image)
            image = Image.open(image)
        elif isinstance(image, (file, File)):
            image = Image.open(image)
        elif isinstance(image, Image):
            pass
        else:
            raise ValueError("Argument of this type is not supported.")
        
        self.delete()
        
        self._loaded_original = image
        
        # Get image type from image, or from parameters 
        if image_type is None:
            image_type = self._loaded_original.format
        
        self.original_image_type = self.get_image_type(ORIGINAL_FORMAT, image_type)
        
        # process original image
        self._loaded_original = self.process_image(ORIGINAL_FORMAT, save=True)
        
        if generate:
            for format in self.formats:
                if format != ORIGINAL_FORMAT:
                    self.process_image(format, save=True)
        
        return self._loaded_original
    
    def process_image(self, format, image=None, save=False):
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
            
            file = self.storage.open(self.get_path(format), mode='wb')
            try:
                image_type = self.get_image_type(format)
                try:
                    image.save(file, format=image_type, **save_params)
                except IOError:
                    if 'optimize' in save_params:
                        del save_params['optimize']
                    if 'progression' in save_params:
                        del save_params['progression']
                    if 'progressive' in save_params:
                        del save_params['progressive']
                    image.convert('RGB').save(file, format=image_type, **save_params)
            finally:
                file.close()
        
        return image
    
    def get_size(self, format, image=None):
        " TODO: cache this"
        path = self.get_path(format)
        if format != ORIGINAL_FORMAT and not self.storage.exists(path):
            image = self.process_image(format, save=True)
            return image.size
        else:
            return get_image_dimensions(self.storage.open(path))
    
    def load_original(self):
        if not self:
            return None
        if not self._loaded_original:
            image = self.storage.open(self.get_path(ORIGINAL_FORMAT))
            self._loaded_original = Image.open(image)
        return self._loaded_original
    
    def delete(self):
        """
        Mark wallet as not saved and delete all files
        """
        if not self:
            return
        for format in self.formats:
            path = self.get_path(format)
            self.storage.delete(path)
        self.original_image_type = False
        self._loaded_original = False
    
    def clean(self, format):
        """
        Delete not-original images from disk.
        """
        if not self or format == ORIGINAL_FORMAT:
            # Use delete() instead.
            return
        path = self.get_path(format)
        self.storage.delete(path)
    
    def get_url(self, format):
        # url returns only for existing images
        if self:
            path = self.get_path(format)
            # if image not found, it created
            if format != ORIGINAL_FORMAT and not self.storage.exists(path):
                self.process_image(format, save=True)
            return self.storage.url(path)
        else:
            return None
    
    def get_path(self, format):
        extension = self.image_types_extensions[self.get_image_type(format)]
        return self.pattern % {'size': format, 'extension': extension}
    
    def get_image_type(self, format, original_image_type=None):
        if not format in self.formats:
            raise AttributeError("%s has no format %s" % (self.__class__.__name__, format))
        
        # for regular format returns custom image type
        if format != ORIGINAL_FORMAT and isinstance(self.formats[format][-1], basestring):
            return self.formats[format][-1]
        
        # next is original format. Return original_image_type, if already saved
        if not self.original_image_type is False:
            return self.original_image_type
        
        # if don't saved, return custom image type for original format
        if isinstance(self.formats[ORIGINAL_FORMAT][-1], basestring):
            return self.formats[ORIGINAL_FORMAT][-1]
        
        if original_image_type:
            return original_image_type
        
        # else fall back
        return self.image_type_fallback


def reverse_curry(_curried_func, *moreargs, **morekwargs):
    def _curried(*args, **kwargs):
        return _curried_func(*(args+moreargs), **dict(kwargs, **morekwargs))
    return _curried

def Filter(filter, *args, **kwargs):
    from imagewallet import filters
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

