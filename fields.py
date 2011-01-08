# -*- coding: utf-8 -*-

from django.db.models import Field
from django.db.models.fields.files import FileField
from django.db.models import signals
from django.core.files import File
from django.utils.encoding import force_unicode, smart_str
from imagewallet import Wallet, Filter, ORIGINAL_FORMAT
from imagewallet.forms import WalletFileField

import os
import datetime
import random

class WalletDescriptor(object):
    def __init__(self, field):
        self.field = field
    
    def __get__(self, obj=None, type=None):
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
            pattern = os.path.join(field.upload_to, field.pattern % vars)
        
        value = field.attr_class(field.formats, pattern, original_format, field.storage)
        
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
    
    def __init__(self, formats={}, verbose_name=None, name=None,
                 upload_to='', storage=None, generate_on_save=False,
                 max_width=None, max_height=None, max_square=None,
                 pattern=None, **kwargs):
        for arg in ('primary_key',):
            if arg in kwargs:
                raise TypeError("'%s' is not a valid argument for %s." % (arg, self.__class__))        
        
        self.upload_to = upload_to or 'thumbs'
        self.storage = storage
        self.generate_on_save = generate_on_save
        
        self.formats = {
            ORIGINAL_FORMAT: (
                Filter('quality', 95),
            ),
        }
        self.formats.update(formats)
        self.max_width = max_width
        self.max_height = max_height
        self.max_square = max_square
        self.pattern = pattern or "%(hash1)s/%(hash2)s%(hash3)s_%(size)s.%(extension)s"
        kwargs['max_length'] = kwargs.get('max_length', 255) 
        
        Wallet.populate_formats(self.formats.keys())
        
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






class FieldWallet(Wallet):
    def __init__(self, instance, field, *args, **kwargs):
        super(FieldWallet, self).__init__(field.formats, storage=field.storage, *args, **kwargs)
        self.instance = instance
        self.field = field
        
    def save(self, name, image, save=False):
        self.delete(save=False)
        self.pattern = self.field.generate_filename(self.instance, name)
        super(FieldWallet, self).save(image, self.field.process_all_formats)
        if save:
            self.instance.save()
    save.alters_data = True
    
    def copy(self, wallet):
        if self:
            raise ValueError("Can not save another images in saved wallet. Delete first.")
        if not wallet:
            return
        self.pattern = self.field.generate_filename(self.instance, wallet.get_path(ORIGINAL_FORMAT))
        super(FieldWallet, self).copy(wallet)
    
    def delete(self, save=True):
        super(FieldWallet, self).delete()
        if save:
            self.instance.save()
    delete.alters_data = True

class NewWalletDescriptor(object):
    def __init__(self, field):
        self.field = field
    
    def __get__(self, instance=None, owner=None):
        field = self.field
        wallet = value = instance.__dict__[field.name]
        # In most cases strings and Nones comes from database
        if isinstance(value, basestring) or value is None:
            pattern = None
            format = False
            if value:
                try:
                    pattern, format = value.rsplit(';', 1)
                except ValueError:
                    pass
            wallet = field.attr_class(instance, field, pattern, format)
            instance.__dict__[field.name] = wallet
        # value uploaded from form
        elif isinstance(value, File):
            wallet = field.attr_class(instance, field)
            wallet.save(value.name, value, save=False)
            instance.__dict__[field.name] = wallet        
        # copy image from foreign wallets
        elif isinstance(value, Wallet) and (not isinstance(value, field.attr_class) or value.instance != instance or value.field != field):
            wallet = self.field.attr_class(instance, self.field)
            wallet.copy(value)
        return wallet
    
    def __set__(self, instance, value):
        instance.__dict__[self.field.name] = value
    
    def __delete__(self, instance):
        return self.__set__(instance, None)
    
class NewWalletField(FileField):
    attr_class = FieldWallet
    descriptor_class = NewWalletDescriptor
    random_chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
    random_sings = 12
    
    def __init__(self, verbose_name=None, name=None, upload_to='', storage=None, 
                 formats={}, process_all_formats=False, **kwargs):
        kwargs.setdefault('max_length', 255)
        unique = kwargs.pop('unique', False)
        # set upload_to to empty string to prevent wrong handle
        super(NewWalletField, self).__init__(verbose_name, name, '', storage, **kwargs)
        # unlike file fields, wallet fields can be unique
        self._unique, self.upload_to = unique, upload_to
        if callable(upload_to):
            self.get_directory_name = upload_to
        
        self.formats = {
            ORIGINAL_FORMAT: (
                Filter('quality', 95),
            ),
        }
        self.formats.update(formats)
        self.process_all_formats = process_all_formats
        self.attr_class.populate_formats(self.formats.keys())
    
    def pre_save(self, model_instance, add):
        value = model_instance.__dict__[self.name]
        if value is None or isinstance(value, basestring):
            # instance.__dict__ may contain string and null if no one access
            # to field since object loading from database
            return value
        # in other cases in can be anything
        return getattr(model_instance, self.attname)
    
    def get_prep_value(self, value):
        if value is None:
            return None
        if isinstance(value, self.attr_class):
            value = unicode(value)
            if not value and self.null:
                # auto-convert empty wallets to null for null fields
                return None
            return value
        return unicode(value)

    def delete_file(self, instance, sender, **kwargs):
        # connected to post_delete signal
        wallet = getattr(instance, self.name)
        wallet.delete(save=False)
    
    def get_directory_name(self, instance):
        upload_to = smart_str(self.upload_to)
        while '%r' in upload_to:
            upload_to = upload_to.replace('%r', random.choice(self.random_chars), 1)
        return os.path.normpath(force_unicode(datetime.datetime.now().strftime(upload_to)))

    def get_filename(self, filename):
        " Generated name MUST contain %(size)s and %(extension)s replaces "
        hash = "".join([random.choice(self.random_chars) for x in xrange(self.random_sings)])
        return hash + u'_%(size)s.%(extension)s'

    def generate_filename(self, instance, filename):
        """
        generate_filename for wallet is more intelligent then for files.
        """
        dir = self.get_directory_name(instance)
        filename = os.path.basename(filename or '')
        while True:
            file = os.path.join(dir, self.get_filename(filename))
            # it is stupid, to check all extensions, but 
            if not any((self.storage.exists(file % {'size': ORIGINAL_FORMAT, 'extension': extension}) for extension in self.attr_class.image_types_extensions.values())):
                break
        return file
        
    def south_field_triple(self):
        "Returns a suitable description of this field for South."
        # We'll just introspect the _actual_ field.
        from south.modelsinspector import introspector
        field_class = self.__class__.__module__ + "." + self.__class__.__name__
        args, kwargs = introspector(self)
        # That's our definition!
        return (field_class, args, kwargs)
