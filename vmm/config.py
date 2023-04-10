from pathlib import Path
from typing import Dict, Any, List
import json

from pydantic import BaseSettings
from xdg_base_dirs import xdg_config_home, xdg_config_dirs
import toml


class Config(BaseSettings):

    connect_uri: str = "qemu:///system"
    """ The URL of the libvirt connection """
    noninteractive_editor: List[str] = ["alacritty", "-e", "vim"]

    @classmethod
    def locate_config(cls) -> Path:

        for path in [xdg_config_home(), *list(xdg_config_dirs())]:
            cfg_path = path / "vmm" / "config.toml"
            if cfg_path.is_file():
                return cfg_path

        return xdg_config_home() / "vmm" / "config.toml"

    def save(self):
        """Save the current configuration to the user config directory"""

        cfg_path = Config.locate_config()
        cfg_path.parent.mkdir(parents=True, exist_ok=True)

        with cfg_path.open("w") as filp:
            toml.dump(json.loads(self.json()), filp)

    class Config:
        env_prefix = "RICE_"
        """ Environment variable prefix """
        env_file_encoding = "utf-8"

        @classmethod
        def customise_sources(cls, init_settings, env_settings, file_secret_settings):
            return (
                init_settings,
                xdg_toml_settings_source,
                env_settings,
                file_secret_settings,
            )


def xdg_toml_settings_source(settings: BaseSettings) -> Dict[str, Any]:
    """
    Load settings from a configuration file under one of the XDG config directories.

    Precedence is given to the XDG_CONFIG_HOME, and then to system XDG directories.
    """

    for path in [xdg_config_home(), *list(xdg_config_dirs())]:
        try:
            with (path / "vmm" / "config.toml").open(
                "r", encoding=settings.__config__.env_file_encoding
            ) as filp:
                return toml.load(filp)
        except (PermissionError, FileNotFoundError):
            continue

    return {}
