from typing import Iterable, Any
from abc import ABC, abstractclassmethod
import subprocess

from loguru import logger

from vmm.wofi import wofi, Mode, WofiError
from vmm.fzf import iterfzf


class Item(object):
    def __init__(
        self,
        text: str,
        icon: str | None = None,
        bold: bool = False,
        extra: Any | None = None,
    ):
        self.icon = icon
        self.text = text
        self.bold = bold
        self.extra = extra


class Provider(ABC):
    @abstractclassmethod
    def prompt(cls, prompt: str, options: Iterable[Item]):
        pass

    @abstractclassmethod
    def ask(cls, prompt: str, options: Iterable[Item] | None = None):
        pass

    @abstractclassmethod
    def notify(cls, message: str, **kwargs):
        pass


class Wofi(Provider):
    """Wofi Menu Provider"""

    @classmethod
    def _build_wofi_item(cls, item: Item) -> str:
        if item.bold:
            text = "<b>" + item.text + "</b>"
        else:
            text = item.text

        if item.icon:
            icon = f"img:{item.icon}:text:"
        else:
            icon = ""

        return icon + text

    @classmethod
    def prompt(cls, prompt: str, options: Iterable[Item]):
        try:

            items = {cls._build_wofi_item(item): item for item in options}

            result = wofi(
                mode=Mode.DMENU,
                allow_images=True,
                allow_markup=True,
                parse_search=True,
                options=items.keys(),
                prompt=prompt,
            )

            return items.get(result, None)
        except WofiError:
            return None


class Fzf(Provider):
    """fzf Menu Provider"""

    @classmethod
    def prompt(cls, prompt: str, options: Iterable[Item]):
        itemmap = {}

        def build_items(items: Iterable[Item]) -> Iterable[str]:
            for item in items:
                itemmap[item.text] = item
                yield item.text

        return itemmap.get(iterfzf(build_items(options), prompt=prompt))

    @classmethod
    def ask(cls, prompt: str, options: Iterable[Item] | None = None) -> str:

        return iterfzf(
            (item.text for item in options) if options else [""],
            prompt=prompt,
            print_query=True,
            exact=False,
        )[0]

    @classmethod
    def notify(cls, message: str, **kwargs):

        try:
            subprocess.run(
                [
                    "notify-send",
                    "Virtual Machine Manager",
                    message.format(**kwargs),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            logger.info(message, **kwargs)
