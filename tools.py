# -*- coding: utf-8 -*-

from django.db.models.loading import get_apps, get_models
from django.db.models import Q

from imagewallet import Wallet


def collect_fields(includes=[], klass=None):
    for app in get_apps():
        app_name = app.__name__.split('.')[-2].lower()
        for model in get_models(app):
            model_name = model.__name__.lower()
            for field in model._meta.fields:
                field_name = field.name.lower()
                if not klass or isinstance(field, klass):
                    for include in includes:
                        if (not include[0] or include[0] == app_name) \
                            and (not include[1] or include[1] == model_name) \
                            and (not include[2] or include[2] == field_name):
                            yield field
                            break


def collect_wallets(fields, klass=Wallet):
    for field in fields:
        model = field.model
        exclude = Q(**{field.name: None})
        if not field.null:
            exclude = exclude | Q(**{field.name: ''})
        items = model._default_manager.exclude(exclude).values(model._meta.pk.name, field.name)
        for item in items:
            pattern, format = item.get(field.name).rsplit(';', 1)
            yield klass(field.formats, pattern, format, storage=field.storage)
