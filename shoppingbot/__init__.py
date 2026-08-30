#!/usr/bin/env python3

import sys
import os
import signal
import logging
import asyncio
import argparse

import argcomplete

from .bot import ShoppingBot


_DEFAULT_LOG_FORMAT = "%(name)s : %(threadName)s : %(levelname)s : %(message)s"

logging.basicConfig(
    stream=sys.stderr,
    format=_DEFAULT_LOG_FORMAT,
    level=logging.INFO,
)


class ShoppingBotApp:
    def __init__(self, args):
        args = self._parseArguments(args)
        logging.getLogger().setLevel(args.verbosity)

        logging.info("Shopping List Bot is starting up")

        self._token = self._get_token(args.token)

        # Don't create asyncio objects or the bot here.
        # asyncio.run() hasn't created the event loop yet.
        self._bot = None
        self._bot_task = None
        self._shutdown_event = None

    def _get_token(self, token_or_file):
        try:
            if os.path.exists(token_or_file):
                with open(token_or_file, "r") as f:
                    token = f.read().strip("\n\r")
                    logging.debug("Read token from file %s", token_or_file)
                    return token
        except Exception:
            logging.exception("Failed to read parameter token as file")

        logging.debug("Using token from the command line")
        return token_or_file

    def _parseArguments(self, args):
        parser = argparse.ArgumentParser()

        parser.add_argument(
            "--verbose",
            dest="verbosity",
            action="store_const",
            const=logging.DEBUG,
        )

        parser.add_argument(
            "--quiet",
            dest="verbosity",
            action="store_const",
            const=logging.ERROR,
        )

        parser.add_argument(
            "token",
            help="Token or path to the file containing the token",
        )

        parser.set_defaults(verbosity=logging.INFO)

        argcomplete.autocomplete(parser)

        return parser.parse_args(args)

    def _quit(self, signum):
        logging.info("Shutting down due to signal %s", signum)

        # This is now created inside the same loop as run().
        if self._shutdown_event is not None:
            self._shutdown_event.set()

    async def run(self):
        # Everything below this point runs inside the event loop
        # created by asyncio.run().

        loop = asyncio.get_running_loop()

        self._shutdown_event = asyncio.Event()

        # Create the bot here, NOT in __init__.
        self._bot = ShoppingBot(self._token)

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(
                    sig,
                    self._quit,
                    sig.name,
                )
            except NotImplementedError:
                # Signal handlers aren't supported by all event loops
                # (notably some Windows configurations).
                pass

        self._bot_task = asyncio.create_task(
            self._bot.message_loop(),
            name="shopping-bot",
        )

        logging.debug("Listening for events")

        try:
            await self._shutdown_event.wait()

        finally:
            logging.info("Stopping shopping bot")

            if self._bot_task is not None:
                self._bot_task.cancel()

                try:
                    await self._bot_task
                except asyncio.CancelledError:
                    pass


def main():
    app = ShoppingBotApp(sys.argv[1:])
    asyncio.run(app.run())
