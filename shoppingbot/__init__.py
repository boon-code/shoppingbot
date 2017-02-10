#!/usr/bin/env python3

import sys
import signal
import logging
import asyncio
import argparse
import functools
import argcomplete
from .bot import ShoppingBot


_DEFAULT_LOG_FORMAT = "%(name)s : %(threadName)s : %(levelname)s : %(message)s"
logging.basicConfig( stream = sys.stderr
                   , format = _DEFAULT_LOG_FORMAT
                   , level = logging.INFO
                   )


class ShoppingBotApp(object):
    def __init__(self, args):
        args = self._parseArguments(args)
        logging.getLogger().setLevel(args.verbosity)
        logging.info("Shopping List Bot is starting up")
        self._bot = ShoppingBot(args.token)
        self._loop = asyncio.get_event_loop()
        self._loop.create_task(self._bot.message_loop())
        logging.debug("Listening for events")

    def _parseArguments(self, args):
        parser = argparse.ArgumentParser()
        parser.add_argument( '--verbose'
                           , dest = 'verbosity'
                           , action = 'store_const'
                           , const = logging.DEBUG
                           )
        parser.add_argument( '--quiet'
                           , dest = 'verbosity'
                           , action = 'store_const'
                           , const = logging.ERROR
                           )
        parser.add_argument('token')
        parser.set_defaults(verbosity=logging.INFO)
        try:
            args = parser.parse_args(args)
            argcomplete.autocomplete(parser)
            return args
        except argparse.ArgumentError as e:
            logging.error("Illegal argument(s): {0}".format(e))
            raise e

    def _quit(self, signum):
        logging.info("Shutting down due to signal {}".format(signum))
        self._loop.stop()

    def run_forever(self):
        self._loop.add_signal_handler( signal.SIGINT
                                     , functools.partial(self._quit, 'SIGINT')
                                     )
        self._loop.run_forever()


def main():
    sb = ShoppingBotApp(sys.argv[1:])
    sb.run_forever()
