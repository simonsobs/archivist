from .storage_disk import StorageDisk
from .storage_hpss import StorageHPSS

storage_factory = {"hpss:": StorageHPSS, "posix": StorageDisk}
