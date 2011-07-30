from django.core.management.base import BaseCommand, CommandError

from imagewallet.fields import WalletField
from imagewallet.tools import collect_fields, collect_wallets
from optparse import make_option

class Command(BaseCommand):
    option_list = BaseCommand.option_list + (
        make_option('-l', '--list', action='append', default=[],
                    help=u'App or app.model or app.model.field to export. Can be specified many times.'),
        make_option('-f', '--format', default='',
                    help=u'Export "original" or other formats, divided by comma. By default exports all formats.'),
        make_option('-a', '--all', action='store_true', default=False,
                    help=u'List all images. No matter, exists they or not.')
    )
    
    def handle(self, **options):
        exports = []
        for export in options['list']:
            export = [None if path in ('*', '') else path for path in export.lower().split('.')]
            exports.append(export + [None] * (3 - len(export)))
        if not exports:
            exports = [[None, None, None]]
        fields = collect_fields(exports, klass=WalletField)
        formats = options['format'].split(',') if options['format'] else None 
        for wallet in collect_wallets(fields):
            for format in wallet.formats:
                if not formats or format in formats:
                    path = wallet.get_path(format)
                    if options['all'] or wallet.storage.exists(path):
                        print path