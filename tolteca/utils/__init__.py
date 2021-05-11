#!/usr/bin/env python

from tollan.utils.fmt import pformat_yaml
from tollan.utils import rupdate
from tollan.utils.log import get_logger
from tollan.utils.dirconf import DirConfError, DirConfMixin

from ..version import version
from astropy.time import Time
import appdirs
from pathlib import Path
from cached_property import cached_property
from schema import Use, Optional, Schema
from copy import deepcopy
import yaml


def get_pkg_data_path():
    """Return the package data path."""
    return Path(__file__).parent.parent.joinpath("data")


def get_user_data_dir():
    return Path(appdirs.user_data_dir('tolteca', 'toltec'))


class RuntimeContextError(DirConfError):
    """Raise when errors occur in `RuntimeContext`."""
    pass


class RuntimeContext(DirConfMixin):
    """A class to manage runtime contexts.

    This class manages a set of configurations in a coherent way, providing
    per-project persistence for user settings.

    A runtime context can be constructed either from file system,
    using the `tollan.utils.dirconf.DirConfMixin` under the hood, or
    be constructed directly from a configuration dict composed
    programatically. Property :attr:``is_persistent`` is set to True in the
    former case.

    """

    _contents = {
        'bindir': {
            'path': 'bin',
            'type': 'dir',
            'backup_enabled': False
            },
        'caldir': {
            'path': 'cal',
            'type': 'dir',
            'backup_enabled': False
            },
        'logdir': {
            'path': 'log',
            'type': 'dir',
            'backup_enabled': False
            },
        'setup_file': {
            'path': '50_setup.yaml',
            'type': 'file',
            'backup_enabled': True
            },
        }

    logger = get_logger()

    def __init__(self, rootpath=None, config=None):
        if sum([rootpath is None, config is None]) != 1:
            raise RuntimeContextError(
                    "one and only one of rootpath and config has to be set")
        if rootpath is not None:
            # we expect that rootpath is already setup if constructed
            # this way.
            try:
                rootpath = self.populate_dir(
                        rootpath,
                        create=False, force=True)
            except DirConfError:
                raise RuntimeContextError(
                        f'missing runtime context contents in {rootpath}. '
                        f'Use {self.__class__.__name__}.from_dir '
                        f'with create=True instead.'
                        )
        self._rootpath = rootpath
        # we delay the validating of config to accessing time
        # in property ``config``
        self._config = config

    @property
    def is_persistent(self):
        """True if this context is created from a valid rootpath."""
        return self._rootpath is not None

    @property
    def rootpath(self):
        if self.is_persistent:
            return self._rootpath
        # the config runtime should always be available,
        # since we add that at the end of the config property getter
        return self.config['runtime']['rootpath']

    def __getattr__(self, name, *args):
        # in case the config is not persistent,
        # we return the content paths from the runtime dict
        # make available the content attributes
        if self.is_persistent:
            return super().__getattr__(name, *args)
        if name in self._contents.keys():
            return self.config['runtime'][name]
        return super().__getattribute__(name, *args)

    def __repr__(self):
        if self.is_persistent:
            return f"{self.__class__.__name__}({self.rootpath})"
        # an extra star to indication is not persistent
        return f"{self.__class__.__name__}(*{self.rootpath})"

    @property
    def config_files(self):
        """The list of config files present in the :attr:`config_files`.

        Returns ``None`` if the runtime context is not persistent.

        """
        if self.is_persistent:
            return self.collect_config_files()
        return None

    @cached_property
    def config(self):
        """The runtime context dict.

        """
        if self.is_persistent:
            cfg = self.collect_config_from_files(
                    self.config_files, validate=True
                    )
            # update runtime info
            cfg['runtime'] = self.to_dict()
        else:
            cfg = self.validate_config(self._config)
            # here we also add the runtime dict if it not already exists
            if 'runtime' not in cfg:
                cfg['runtime'] = {
                        attr: None
                        for attr in self._get_to_dict_attrs()
                        }
        self.logger.debug(f"loaded config: {pformat_yaml(cfg)}")
        return cfg

    @classmethod
    def extend_config_schema(cls):
        # this defines a basic schema to validate the config

        def validate_setup(cfg_setup):
            # TODO implement more logic to verify the settings
            if cfg_setup is None:
                cfg_setup = {}

            # check version
            from ..version import version
            # for now we just issue a warning but this will be replaced
            # by actual version comparison.
            if 'version' not in cfg_setup:
                cls.logger.warning("no version info found.")
                cfg_setup['version'] = version
            if cfg_setup['version'] != version:
                cls.logger.warning(
                        f"mismatch of tolteca version "
                        f"{cfg_setup['version']} -> {version}")
            return cfg_setup

        return {
            'setup': Use(validate_setup),
            Optional(object): object
            }

    @classmethod
    def from_dir(
            cls, dirpath, **kwargs
            ):
        """
        Create `RuntimeContext` instance from `dirpath`.

        This is the preferred method to construct `RuntimeContext`
        from arbitrary path.

        For paths that have already setup previous as runtime context,
        use the constructor instead.

        Parameters
        ----------
        dirpath : `pathlib.Path`, str
            The path to the work directory.
        **kwargs : dict, optional
            Additional arguments passed to the underlying
            :meth:`DirConfMixin.populate_dir`.
        """
        dirpath = cls.populate_dir(dirpath, **kwargs)
        return cls(rootpath=dirpath)

    @classmethod
    def from_config(cls, *configs):
        """
        Create `RuntimeContext` instance from a set of configs.

        This method allow constructing `RuntimeContext`
        from multiple configuration dicts.

        For a single config dict, use the constructor instead.

        Parameters
        ----------
        *configs : tuple
            The config dicts.
        """
        cfg = deepcopy(configs[0])
        # TODO maybe we nned to make deepcopy of all?
        for c in configs[1:]:
            rupdate(cfg, c)
        return cls(config=cfg)

    def symlink_to_bindir(self, src, link_name=None):
        """Create a symbolic link of of `src` in :attr:`bindir`.

        """
        src = Path(src)
        if link_name is None:
            link_name = src.name
        dst = self.bindir.joinpath(link_name)
        dst.symlink_to(src)  # note this may seem backward but it is the way
        self.logger.debug(f"symlink {src} to {dst}")
        return dst

    def setup(self, config=None, overwrite=False):
        """Populate the setup file (50_setup.yaml).

        Parameters
        ----------
        config : dict, optional
            Additional config to add to the setup file.
        overwrite : bool
            Set to True to force overwrite the existing
            setup info. Otherwise a `RuntimeContextError` is
            raised.
        """
        # check if already setup
        with open(self.setup_file, 'r') as fo:
            setup_cfg = yaml.safe_load(fo)
            if isinstance(setup_cfg, dict) and 'setup' in setup_cfg:
                if overwrite:
                    self.logger.debug(
                        "runtime context is already setup, overwrite")
                else:
                    raise RuntimeContextError(
                            'runtime context is already setup'
                            )
        if config is None:
            config = dict()
        else:
            config = deepcopy(config)
        rupdate(
            config,
            {
                'setup': {
                    'version': version,
                    'created_at': Time.now().isot,
                    }
            })
        # write the setup context to the setup_file
        with open(self.setup_file, 'w') as fo:
            yaml.dump(config, fo)
        # invalidate the config cache if needed
        # so later self.config will pick up the new setting
        if 'config' in self.__dict__:
            del self.__dict__['config']
        return self
