from .storage import StorageDisk, StorageHPSS

storage_factory = {"hpss:": StorageHPSS, "posix": StorageDisk}
