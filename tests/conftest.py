"""Makes sure every table exists before a test file builds its database.

Base.metadata only knows about models that have actually been imported. Most
of our test files import the one or two they care about, so running a file on
its own leaves out tables that the ones it imported point at with a foreign
key, and create_all blows up. Running the whole suite hides it because some
other file happened to do the import first.

Importing all of them here fixes it for every test file at once, since pytest
loads conftest before any test module.
"""

from database import announcements  # noqa: F401
from database import attendance     # noqa: F401
from database import audit          # noqa: F401
from database import grades         # noqa: F401
from database import models         # noqa: F401
from database import parents        # noqa: F401
from database import scheduling     # noqa: F401
from database import students       # noqa: F401
