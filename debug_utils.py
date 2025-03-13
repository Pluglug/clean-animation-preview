DBG = False
DBG_INIT = False


class Log:
    """Simple Print Logger with colors."""

    class _style:
        """Style definitions for logging."""

        # Base colors can be modified
        # by adding 10 for background or 60 for bright.
        BLACK = 30
        RED = 31
        GREEN = 32
        YELLOW = 33
        BLUE = 34
        MAGENTA = 35
        CYAN = 36
        WHITE = 37

        # Styles
        RESET = 0
        BOLD = 1
        FAINT = 2
        ITALIC = 3
        UNDERLINE = 4
        INVERTED = 7

    @classmethod
    def ansi(cls, *codes: int) -> str:
        """Generates an ANSI escape code string from style codes."""
        return f'\033[{";".join(str(code) for code in codes)}m'

    LINE_LENGTH = 50
    USE_COLORS = True

    @classmethod
    def color_print(cls, color, *args):
        msg = ", ".join(str(arg) for arg in args)
        if not cls.USE_COLORS:
            print(msg)
            return
        color = [color] if not isinstance(color, (tuple, list)) else color
        print(f"{cls.ansi(*color)}{msg}{cls.ansi(cls._style.RESET)}")

    @classmethod
    def info(cls, *args):
        cls.color_print(cls._style.BLUE, *args)

    @classmethod
    def warn(cls, *args):
        cls.color_print(cls._style.YELLOW, *args)

    warning = warn

    @classmethod
    def error(cls, *args):
        cls.color_print(cls._style.RED, *args)

    # --- Additional methods ---

    @classmethod
    def header(cls, *args, title=None):
        print("")
        title_line, msg = cls._gen_section(*args, title=title)
        cls.color_print(
            (cls._style.GREEN, cls._style.BOLD),
            title_line + (f"\n{msg}" if args else ""),
        )

    @classmethod
    def footer(cls, *args, title=None):
        title_line, msg = cls._gen_section(*args, title=title)
        cls.color_print(cls._style.CYAN, (f"{msg}\n" if args else "") + title_line)
        print("")

    @classmethod
    def _gen_section(cls, *args, title=None):
        msg = ", ".join(str(arg) for arg in args).strip()
        section_length = cls.LINE_LENGTH if not args else max(len(msg), cls.LINE_LENGTH)
        title_line = (
            title.center(section_length, "-")
            if title is not None
            else "-" * section_length
        )
        return title_line, msg
