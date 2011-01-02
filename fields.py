# -*- coding: utf-8 -*-

from django.db.models import Field, SubfieldBase
from django.db.models.fields.files import ImageField, ImageFieldFile
from django.db.models import signals
from django.core.files import File
from django.utils.encoding import force_unicode
from imagewallet import Wallet, Filter, ORIGINAL_SIZE_NAME
from imagewallet.forms import WalletFileField

from os import path as os_path
import random

class WalletDescriptor(object):
    def __init__(self, field):
        self.field = field
    
    def __get__(self, obj=None, type=None):
        if obj is None:
            raise AttributeError('Can only be accessed via an instance.')
        
        value = obj.__dict__[self.field.name]
        
        if isinstance(value, Wallet):
            return value
        
        original_format = False
        field = self.field
        
        if value:
            pattern, original_format = value.split(';')[:2]
        else:
            hash = "".join([random.choice('abcdef0123456789') for x in xrange(32)])
            vars = {'hash1': hash[0:2], 'hash2': hash[2:4], 'hash3': hash[4:],
                    'size': '%(size)s', 'extension': '%(extension)s'}
            pattern = os_path.join(field.upload_to, field.pattern % vars)
        
        value = field.attr_class(field.sizes, pattern, original_format, field.storage)
        
        obj.__dict__[field.name] = value
        
        return obj.__dict__[field.name]

    def __set__(self, obj, value):
        # For file we need save it to exist object 
        if isinstance(value, File):
            wallet = getattr(obj, self.field.name)
            # TODO::  file size checks need be there
            wallet.save(value, generate=self.field.generate_on_save)
        else:
            obj.__dict__[self.field.name] = value
        
    def __delete__(self, obj):
        wallet = getattr(obj, self.field.name)
        wallet.delete()



class WalletField(Field):
    attr_class = Wallet
    descriptor_class = WalletDescriptor
    
    def __init__(self, sizes={}, verbose_name=None, name=None,
                 upload_to='', storage=None, generate_on_save=False,
                 max_width=None, max_height=None, max_square=None,
                 pattern=None, **kwargs):
        for arg in ('primary_key',):
            if arg in kwargs:
                raise TypeError("'%s' is not a valid argument for %s." % (arg, self.__class__))        
        
        self.upload_to = upload_to or 'thumbs'
        self.storage = storage
        self.generate_on_save = generate_on_save
        
        self.sizes = {ORIGINAL_SIZE_NAME: (Filter('quality', 95),)}
        self.sizes.update(sizes)
        self.max_width = max_width
        self.max_height = max_height
        self.max_square = max_square
        self.pattern = pattern or "%(hash1)s/%(hash2)s%(hash3)s_%(size)s.%(extension)s"
        kwargs['max_length'] = kwargs.get('max_length', 255) 
        
        Wallet.populate_sizes(self.sizes.keys())
        
        return super(WalletField, self).__init__(verbose_name, name, **kwargs)
    
    def clean(self, value, model_instance):
        value = super(WalletField, self).clean(value, model_instance)
        return value
    
    def get_prep_value(self, value):
        if value is None:
            return value
        if isinstance(value, Wallet):
            value = unicode(value)
            if not value and self.null:
                return None
        return value
    
    def save_form_data(self, instance, data):
        if data:
            setattr(instance, self.name, data)
    
    def get_internal_type(self):
        return 'FileField'
    
    def contribute_to_class(self, cls, name):
        super(WalletField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, self.descriptor_class(self))
        signals.post_delete.connect(self.delete_file, sender=cls)
        
    def delete_file(self, instance, sender, **kwargs):
        wallet = getattr(instance, self.name)
        wallet.delete()
    
    def formfield(self, **kwargs):
        defaults = {'form_class': WalletFileField}
        defaults.update(kwargs)
        return super(WalletField, self).formfield(**defaults)
    
    def south_field_triple(self):
        "Returns a suitable description of this field for South."
        # We'll just introspect the _actual_ field.
        from south.modelsinspector import introspector
        field_class = self.__class__.__module__ + "." + self.__class__.__name__
        args, kwargs = introspector(self)
        # That's our definition!
        return (field_class, args, kwargs)
    