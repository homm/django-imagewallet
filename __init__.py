# -*- coding: utf-8 -*-

from exceptions import IncorrectLoaded

from django.utils.encoding import force_unicode
from django.utils.functional import curry
from django.core.files.base import ContentFile, StringIO
from django.core.files.storage import default_storage
from django.core.files import File
from django.core.files.images import get_image_dimensions

import PIL

ORIGINAL_FORMAT = 'original'
MAXBLOCK = 3200*2000 # max block size for jpeg save in PIL

class Wallet(object):
    
    # used for files in supported for load formats and don't supported for save (bmp, tiff, etc.)
    image_type_fallback = 'PNG'
    image_types_extensions = {
        'PNG':  'png',
        'JPEG': 'jpg',
    }
    # Original Image, stored after saving or loaded from disk
    _loaded_original = False
    
    def __init__(self, formats_filters, pattern=None, formats_info=None, storage=None):
        """
        Construct new wallet.
        
        formats_filters is required. Dictionary with lists of filters for 
            every format.
        pattern is a string with 2 replaces: "format" and "extension". Used for
            name generation for files.
        formats_info is dictionary with short info about existed images:
            ('image_format', width, height)
        """
        self.formats_filters = formats_filters
        self._pattern = pattern
        self.formats_info = formats_info
        self.storage = storage or default_storage
        
        if formats_info is not None and not pattern:
            raise ValueError('You can not specify formats_info without pattern')
        
        if pattern and '%(format)s' not in pattern:
            raise ValueError('Pattern string should contain %%(format)s '
                             'replace. Given pattern: %s' % pattern)
    
    def get_pattern(self):
        return self._pattern
    
    def set_pattern(self, value):
        if self:
            raise ValueError("Can not change pattern for saved wallet.")
        self._pattern = value
    
    pattern = property(get_pattern, set_pattern)
    
    def __nonzero__(self):
        """
        When any image loaded, formats_info is dict with at least one element.
        """
        return self.formats_info is not None
    
    def __unicode__(self):
        if self:
            return self.get_path(ORIGINAL_FORMAT)
        else:
            return u''
    
    @classmethod
    def populate_formats(cls, formats):
        cls = Wallet
        for format in formats:
            url = 'url_%s' % format
            if not hasattr(cls, url):
                setattr(cls, url, property(curry(cls.get_url, format=format)))
            path = 'path_%s' % format
            if not hasattr(cls, path):
                setattr(cls, path, property(curry(cls.get_path, format=format)))
            size = 'size_%s' % format
            if not hasattr(cls, size):
                setattr(cls, size, property(curry(cls.get_size, format=format)))
    
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
        Return original image.
        """
        if self:
            raise ValueError("Can not save another images in saved wallet.")
        
        if not self._pattern:
            raise ValueError("Pattern should be present.")
        
        if '%(format)s' not in self._pattern:
            raise ValueError('Pattern string should contain %%(format)s '
                ' replace. Given pattern: %s' % self._pattern)
    
        if isinstance(image, basestring):
            image = self.storage.open(image)
            image = PIL.Image.open(image)
        elif isinstance(image, (file, File)):
            image = PIL.Image.open(image)
        elif isinstance(image, PIL.Image):
            pass
        else:
            raise ValueError("Argument of this type is not supported.")

        self.original_image_type = self.get_format_type(ORIGINAL_FORMAT, self._loaded_original.format)
        
        # process original image
        self._loaded_original = self.process_format(ORIGINAL_FORMAT, image, save=True)
        
        return self._loaded_original
    
    def process_format(self, format, image=None, save=False):
        """
        Process image, make one thumb from given format 
        """
        if image is None:
            image = self.load_original()
        
        if not image:
            return image
        
        for filter in self.formats_filters[format]:
            if callable(filter):
                image = filter(image)
        
        if save:
            save_params = image.info
            
            # Save empty file to ensure path is exists
            path = self.get_path(format)
            self.storage.save(path, ContentFile(''))
            file = self.storage.open(path, mode='wb')
            try:
                image_type = self.get_format_type(format)
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
                    
                info = (image_type,) + image.size
                if not self:
                    self.formats_info = {}
                self.formats_info[format] = info
                
            finally:
                file.close()
        
        return image
    
    def process_all_formats(self):
        for format in self.formats_filters:
            if format != ORIGINAL_FORMAT:
                self.process_format(format, save=True)
    
    def copy(self, wallet):
        """
        Copy image from other wallet to this without changing. Filters for original format ignored.
        """
        if self:
            raise ValueError("Can not save another images in saved wallet.")
        if not wallet:
            return
        self.formats_info = {
            ORIGINAL_FORMAT: wallet.formats_info[ORIGINAL_FORMAT]
        }
        _from = wallet.get_path(ORIGINAL_FORMAT)
        _to = self.get_path(ORIGINAL_FORMAT)
        self.storage.save(_to, wallet.storage.open(_from))
        
    def delete(self):
        """
        Mark wallet as not saved and delete all files
        """
        if not self:
            return
        for format in self.formats_filters:
            path = self.get_path(format)
            self.storage.delete(path)
        self.formats_info = None
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
    
    def get_size(self, format):
        if not self.formats_info:
            return (None, None)
        if format not in self.formats_info:
            self.process_format(format, save=True)
        # first element — image type. We need second and third.
        return self.formats_info[format][1:3]
    
    def get_url(self, format):
        """
        Method return url to given image format. If image does not exists, 
        it created. This is external interface.
        """
        if not self.formats_info:
            return
        if format not in self.formats_info:
            self.process_format(format, save=True)
        path = self.get_path(format)
        return self.storage.url(path)
    
    def get_path(self, format):
        """
        Method returns path to given image format even if it does not exists.
        This method for internal use and files manipulations.
        """
        type = self.get_format_type(format)
        extension = self.image_types_extensions[type]
        return self._pattern % {'format': format, 'extension': extension}
    
    def get_format_type(self, format, new_image_type=False):
        # image loaded
        if self:
            # format prepared or format is ORIGINAL_FORMAT
            if format in self.formats_info:
                return self.formats_info[format][0]
            
            # if type defined in last filter of format 
            last_filter = self.formats_filters[format][-1]
            if isinstance(last_filter, basestring):
                return last_filter
            
            # original format always should be in formats_info
            return self.formats_info[ORIGINAL_FORMAT][0]
        
        elif format == ORIGINAL_FORMAT:
            # if type defined in last filter of format 
            last_filter = self.formats_filters[format][-1]
            if isinstance(last_filter, basestring):
                return last_filter
            
            # new_image_type is type for just loaded image
            if new_image_type and new_image_type in self.image_types_extensions:
                return new_image_type
        
            # for unsupported types it will be png
            return self.image_type_fallback
        
        else:
            raise AttributeError('Try get image type for not loaded image. '
                'Format: %s' % format)
    
    def get_format_info(self, format):
        if format in self.formats_info:
            return self.formats_info[format]
        


def reverse_curry(_curried_func, *moreargs, **morekwargs):
    def _curried(*args, **kwargs):
        return _curried_func(*(args+moreargs), **dict(kwargs, **morekwargs))
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

