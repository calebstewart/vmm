from pathlib import Path
from enum import Enum
import subprocess


class WofiError(Exception):
    pass


class Mode(str, Enum):
    """Wofi Menu Modes"""

    DMENU = "dmenu"
    DRUN = "drun"
    RUN = "run"


class Matching(str, Enum):

    CONTAINS = "contains"
    MULTI = "multi-contains"
    FUZZY = "fuzzy"


class Location(str, Enum):

    CENTER = "center"
    TOP_LEFT = "top_left"
    TOP = "top"
    TOP_RIGHT = "top_right"
    RIGHT = "right"
    BOTTOM_RIGHT = "bottom_right"
    BOTTOM = "bottom"
    BOTTOM_LEFT = "bottom_left"
    LEFT = "left"


class Sort(str, Enum):

    DEFAULT = "default"
    ALPHABETICAL = "alphabetical"


def wofi(
    mode: Mode,
    width: int | None = None,
    height: int | None = None,
    offset: tuple[int, int] | None = None,
    allow_images: bool = False,
    allow_markup: bool = False,
    cache_file: Path | None = None,
    term: Path | None = None,
    password: bool | str | None = None,
    exec_search: bool = False,
    hide_scroll: bool = False,
    matching: Matching = Matching.CONTAINS,
    insensitive: bool = False,
    parse_search: bool = False,
    location: Location = Location.CENTER,
    lines: int | None = None,
    columns: int | None = None,
    sort_order: Sort = Sort.DEFAULT,
    dark: bool | None = None,
    search: str | None = None,
    config: Path | None = None,
    style: Path | None = None,
    colors: Path | None = None,
    options: list[str] | None = None,
):

    args = [
        "wofi",
        "--show",
        mode,
        "--matching",
        str(matching),
        "--location",
        str(location),
        "--sort-order",
        str(sort_order),
    ]

    if width is not None:
        args.extend(["--width", str(width)])
    if height is not None:
        args.extend(["--height", str(height)])
    if offset is not None:
        args.extend(["--xoffset", str(offset[0]), "--yoffset", str(offset[1])])
    if allow_images:
        args.append("--allow-images")
    if allow_markup:
        args.append("--allow-markup")
    if cache_file is not None:
        args.extend(["--cache-file", str(cache_file)])
    if term is not None:
        args.extend(["--term", str(term)])
    if isinstance(password, bool) and password:
        args.extend(["--password", "*"])
    elif isinstance(password, str):
        args.extend(["--password", password[0]])
    if exec_search:
        args.append("--exec-search")
    if hide_scroll:
        args.append("--hide-scroll")
    if insensitive:
        args.append("--insensitive")
    if parse_search:
        args.append("--parse-search")
    if lines is not None:
        args.extend(["--lines", str(lines)])
    if columns is not None:
        args.extend(["--columns", str(columns)])
    if dark:
        args.append("--gtk-dark")
    if search is not None:
        args.extend(["--search", search])
    if config is not None:
        args.extend(["--config", str(config)])
    if style is not None:
        args.extend(["--style", str(style)])
    if colors is not None:
        args.extend(["--colors", str(colors)])

    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout, stderr = proc.communicate("\n".join(options) if options else None)
    if proc.returncode != 0:
        raise WofiError(stderr)
    else:
        return stdout.strip()
