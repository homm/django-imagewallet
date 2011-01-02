# -*- coding: utf-8 -*-

import filters
from exceptions import IncorrectLoaded

from django.utils.encoding import force_unicode
from django.utils.functional import curry
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files import File
from django.conf import settings
from PIL import Image

from os import path as os_path
from glob import glob

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
    
import ImageFile
ImageFile.MAXBLOCK = 1000000 # fix problem with large images and optimized files

DEFAULT_FORMATS_FOR_SAVE = {
    'PNG':  'png',
    'JPEG': 'jpg',
    'GIF':  'gif',
}

ORIGINAL_SIZE_NAME = 'original'

class Wallet(object):
    # used for files in supported for load formats and don't supported for save (bmp, tiff, etc.)
    image_format_failback = 'PNG'
    formats_for_save = DEFAULT_FORMATS_FOR_SAVE
    # Original Image, stored after saving or loaded from disk
    _loaded_original = False
    
    def __init__(self, sizes, pattern, original_format=False, storage=None):
        """
        Class take 2 impotent parameters: pattern and original_format.
        Pattern is a string with 2 places: for "size" name and for "extension"
        original_format is one of 
        """
        
        if '%(size)' not in pattern or '%(extension)' not in pattern:
            raise IncorrectLoaded('Pattern string must be formatable string with %%(size) and %%(extension) replaces. Given pattern: %s' % pattern)
        
        if original_format is not False and original_format not in self.formats_for_save:
            raise IncorrectLoaded('Original_type should be one of formats_for_save types, or should be False. "%s" given.' % original_type)
        
        self._sizes = sizes
        self._pattern = pattern
        self._original_format = original_format
        self._storage = storage or default_storage
    
    sizes = property(lambda self: self._sizes)
    original_format = property(lambda self: self._original_format)
    exist = property(lambda self: not self._original_format is False)
    
    def get_pattern(self):
        if callable(self._pattern):
            self._pattern = self._pattern()
        return self._pattern
    def set_pattern(self, pattern):
        self._pattern = pattern
    pattern = property(get_pattern, set_pattern)
    
    def __unicode__(self):
        if self.exist:
            return u'%s;%s' % (self.pattern, self._original_format)
        else:
            return ''
    
    def __nonzero__(self):
        return not self._original_format is False
    
    def __reduce__(self):
        """
        Save wallet as string. 
        """
        return (unicode, (self.__unicode__(),))
    
    @classmethod
    def populate_sizes(cls, sizes):
        for size in sizes:
            url_name = 'url_%s' % size
            if not hasattr(cls, url_name):
                setattr(cls, url_name, curry(cls.get_url, size=size))
            path_name = 'path_%s' % size
            if not hasattr(cls, path_name):
                setattr(cls, path_name, curry(cls.get_path, size=size))
 
    def save(self, image, image_format=None, generate=False):
        """
        Loads new image to wallet.
        image may be path to file, file object, django object or pil image
        generate may be True, False, or None
        Returns original image.
        """
        if isinstance(image, basestring):
            image = self._storage.open(image)
            image = Image.open(image)
        elif isinstance(image, (file, File)):
            image = Image.open(image)
        elif isinstance(image, Image):
            pass
        else:
            raise ValueError("Argument of this type is not supported.")
        
        if self.exist:
            self.delete()
        
        self._loaded_original = image
        
        # Get format from image, or from parameters 
        if image_format is None:
            image_format = self._loaded_original.format
        
        self._original_format = self.get_format(ORIGINAL_SIZE_NAME, image_format)
        
        # process original image
        self._loaded_original = self.process_image(ORIGINAL_SIZE_NAME, save=True)
        
        if generate:
            for size in self._sizes:
                if size != ORIGINAL_SIZE_NAME:
                    self.process_image(size, save=True)
        
        return self._loaded_original
    
    def process_image(self, size, image=None, save=False):
        """
        Process image, make one thumb from given size 
        """
        
        if image is None:
            image = self.load_original()
        
        if not image:
            return image
        
        for filter in self._sizes[size]:
            if callable(filter):
                image = filter(image)
        
        if save:
            save_params = image.info
            
            content = StringIO()
            try:
                image.save(content, format=self.get_format(size), **save_params)
            except IOError:
                if 'optimize' in save_params:
                    del save_params['optimize']
                if 'progression' in save_params:
                    del save_params['progression']
                if 'progressive' in save_params:
                    del save_params['progressive']
                image.convert('RGB').save(content, format=self.get_format(size), **save_params)
            content.seek(0)
            self._storage.save(self.get_path(size), ContentFile(content.read()))
        
        return image
    
    def get_size(self, size, image=None):
        if image is None:
            image = self.load_original()
        
        if not image:
            return (0, 0)
        
        return (800, 600)
#       Здесь полный бред, который нужно заменить на генерацию изображения и возврат действительнвх значений
#        
#        image_size = image.size
#        
#        for rule in self._sizes[size]:
#            if isinstance(rule, tuple):
#                filter, args, kwargs = rule
#                
#                if callable(filter):
#                    pass
#                elif callable(getattr(filters, filter, None)):
#                    filter = getattr(filters, filter)
#                else:
#                    raise ValueError("Filter %s not found." % force_unicode(filter))
#                
#                if getattr(filter, 'alter_size', False):
#                    image_size = filter.calc_size(image_size, *args, **kwargs)
#        
#        return image_size
    
    def load_original(self):
        if not self.exist:
            return None
        if not self._loaded_original:
            image = self._storage.open(self.get_path(ORIGINAL_SIZE_NAME))
            self._loaded_original = Image.open(image)
        return self._loaded_original
    
    def delete(self, clean=True):
        """
        Mark wallet as not saved and delete all files
        """
        if not self.exist:
            return
        
        for size in self._sizes:
            path = self.get_path(size)
            if self._storage.exists(path):
                self._storage.delete(path)
        if clean:
            self.clean()
        self._original_format = False
        self._loaded_original = False
    
    def clean(self, size=None):
        """
        Delete not-original images from disk.
        Can be used for cleanup or for regenerate thumbs.
        Return number of deleted thumbs.
        """
        if not self.exist or size == ORIGINAL_SIZE_NAME:
            # Use delete() instead.
            return
        
        if size:
            path = self.get_path(size)
            if self._storage.exists(path):
                self._storage.delete(path)
                return 1
            return 0
        else:
            search = self.pattern % {'size': '*', 'extension': '*'}
            thumbs = glob(self._storage.path(search))
            original_thumb = self._storage.path(self.get_path(ORIGINAL_SIZE_NAME))
            if original_thumb in thumbs:
                thumbs.remove(original_thumb)
            if len(thumbs):
                location = self._storage.path('')
                for thumb in thumbs:
                    if thumb.find(location) == 0:
                        thumb = thumb[len(location):].lstrip('/')
                    self._storage.delete(thumb)
            return len(thumbs)
    
    def get_url(self, size, include_media=True):
        if size not in self._sizes:
            raise AttributeError("%s has no size %s" % (self.__class__.__name__, size))
        # url returns only for existed images
        if self.exist:
            path = self.get_path(size)
            # if image don't found, it created
            if size != ORIGINAL_SIZE_NAME and not self._storage.exists(path):
                self.process_image(size, save=True)
            if include_media:
                return os_path.join(settings.MEDIA_URL, path)
            return path
        else:
            return None
    
    def get_path(self, size):
        if size not in self._sizes:
            raise AttributeError("%s has no size %s" % (self.__class__.__name__, size))
        extension = self.formats_for_save[self.get_format(size)]
        return self.pattern % {'size': size, 'extension': extension}
    
    def get_format(self, size, original_format=None):
        if size not in self._sizes:
            raise AttributeError("%s has no size %s" % (self.__class__.__name__, size))
        
        # for regular sizes returns custom format
        if size != ORIGINAL_SIZE_NAME and isinstance(self._sizes[size][-1], basestring):
            return self._sizes[size][-1]
        
        # next is original size. Return original_format, if already saved
        if not self._original_format is False:
            return self._original_format
        
        # if don't saved, return custom format for original size
        if isinstance(self._sizes[ORIGINAL_SIZE_NAME][-1], basestring):
            return self._sizes[ORIGINAL_SIZE_NAME][-1]
        
        if original_format:
            return original_format
        
        # else simple failback
        return self.image_format_failback


def reverse_curry(_curried_func, *moreargs, **morekwargs):
    def _curried(*args, **kwargs):
        return _curried_func(*(args+moreargs), **dict(kwargs, **morekwargs))
    return _curried

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

