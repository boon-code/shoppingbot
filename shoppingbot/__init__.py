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

        token = self._get_token(args.token)
        self._bot = ShoppingBot(token)

        self._shutdown_event = asyncio.Event()
        self._bot_task = None

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
        return token_or_file  # assume it is a token

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

        try:
            argcomplete.autocomplete(parser)
            return parser.parse_args(args)
        except argparse.ArgumentError as e:
            logging.error("Illegal argument(s): %s", e)
            raise

    def _quit(self, signum):
        logging.info("Shutting down due to signal %s", signum)
        self._shutdown_event.set()

    async def run(self):
        loop = asyncio.get_running_loop()

        # Signal handlers are only available on Unix event loops.
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(
                    sig,
                    self._quit,
                    sig.name,
                )
            except NotImplementedError:
                # Windows' default event loop may not support this.
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

            if self._bot_task and not self._bot_task.done():
                self._bot_task.cancel()

                try:
                    await self._bot_task
                except asyncio.CancelledError:
                    pass


def main():
    app = ShoppingBotApp(sys.argv[1:])
    asyncio.run(app.run())
