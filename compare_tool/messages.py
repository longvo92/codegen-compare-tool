"""English messages with the template and values available to other renderers."""

from typing import Any


class Message(str):
    """Preserve the existing string value at CLI, report and JSON boundaries."""

    template: str
    values: tuple

    def __new__(cls, template: str, *values: Any):
        message = super().__new__(cls, template.format(*values))
        message.template = template
        message.values = values
        return message

    def __getnewargs__(self):
        return (self.template, *self.values)
