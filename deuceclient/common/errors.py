"""
Deuce Client: Errors
"""


class DeuceClientExceptions(Exception):
    """Generic Deuce Client Exception
    """
    pass


class InvalidProject(DeuceClientExceptions):
    """Deuce Client Project-ID Exceptions
    """
    pass


class InvalidVault(DeuceClientExceptions):
    """Deuce Client Vault Exceptions
    """
    pass


class InvalidFiles(DeuceClientExceptions):
    """Deuce Client File Exceptions
    """
    pass


class InvalidBlocks(DeuceClientExceptions):
    """Deuce Client (metadata) Block Exceptions
    """
    pass


class InvalidStorageBlocks(InvalidBlocks):
    """Deuce Client Storage Block Exceptions
    """
    pass


class ParameterConstraintError(DeuceClientExceptions):
    """Parameter Constraint Error
    """
    pass
