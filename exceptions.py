# -*- coding: utf-8 -*-

class WalletException(Exception):
    pass

class IncorrectLoaded(WalletException):
    pass

class SaveError(WalletException):
    pass