"""
Dead simple template engine.
"""

import re
import copy

class Context:
    def __init__(self):
        self.locals = {}
        self.globals = {
            '__builtins__': __builtins__,
        }

    def update(self, other):
        self.locals.update(other)

    def update_globals(self, other):
        self.globals.update(other)

    def expand(self, template):
        return re.sub(r'\{\{(.*?)\}\}', self._replace, template)

    def _replace(self, match):
        expr = match.group(1)
        return str(eval(expr, self.locals, self.globals))

    def copy(self):
        return copy.copy(self)
