from django.core.management.base import BaseCommand, CommandError
from django.db.models.loading import get_app, get_models, get_model
from django.db.models import Q

from imagewallet import ORIGINAL_SIZE_NAME
from imagewallet.fields import WalletField, WalletDescriptor

class Command(BaseCommand):
    args = '[app [model [field [size]]]]'
    help = 'Delete thumbs to save space.'
    
    def handle(self, app_label="", model_label="", field_label="", size_label="", *args, **options):
        if app_label:
            try:
                app = get_app(app_label, emptyOK=True)
            except:
                raise CommandError("application %s not found" % app_label)
        else:
            app_label = None
            app = None
        
        if app_label and model_label:
            model = get_model(app_label, model_label)
            if not model:
                raise CommandError('model "%s" in application "%s" not found' % (model_label, app_label))
            models = [model]
        else:
            model_label = None
            models = get_models(app)
        
        fields = []
        if app_label and model_label and field_label:
            for field in models[0]._meta.fields:
                if field_label == field.name:
                    if isinstance(field, WalletField):
                        fields.append(field)
                        break
                    else:
                        raise CommandError('field "%s" of model "%s" is not a wallet field' % (field_label, model_label))
            if len(fields) == 0:
                raise CommandError('field "%s" not found in model "%s"' % (field_label, model_label))
        else:
            field_label = None
            for model in models:
                for field in model._meta.fields:
                    if isinstance(field, WalletField):
                        fields.append(field)
            if len(fields) == 0:
                raise CommandError('no wallet fields found')        
        
        if not (app_label and model_label and field_label and size_label):
            size_label = None
        
        deleted = 0
        for field in fields:
            model = field.model
#            descriptor = model.__dict__.get(field.name)
            exclude = Q(**{field.name: ''}) | Q(**{field.name: None})
            items = model._default_manager.exclude(exclude).values(model._meta.pk.name, field.name)
            object_item = model()
            try:
                for item in items:
                    setattr(object_item, field.name, item.get(field.name))
                    wallet = getattr(object_item, field.name)
                    deleted += wallet.clean(size_label)
            except AttributeError:
                raise CommandError('size "%s" not found' % size_label)

        print "Deleted %s images from %s fields." % (deleted, len(fields)) 
        print "Done." 
            
                    
        
        
        
        

