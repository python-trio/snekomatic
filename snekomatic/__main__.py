import sys
import trio

from .app import main

# Make sure that print's are flushed immediately so heroku's logging
# infrastructure can see them.
sys.stdout.reconfigure(line_buffering=True)

trio.run(main)
