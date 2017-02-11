import logging
import asyncio
import telepot
from telepot import glance, message_identifier
from telepot.namedtuple import ( InlineKeyboardMarkup
                               , InlineKeyboardButton
                               , ReplyKeyboardMarkup
                               , ReplyKeyboardRemove
                               , KeyboardButton
                               )
from telepot.aio.delegate import ( pave_event_space
                                 , per_chat_id
                                 , create_open
                                 , call
                                 , include_callback_query_chat_id
                                 )

def kbchoice(choices, prefix='', cls=InlineKeyboardButton):
    """ Generates keyboard buttons

    :param choices: a list of tuples to generate keyboard buttons from. First
                    item of each tuple in the list is a key (for processing),
                    second item is the text to display
    :param prefix:  optional prefix which will be prepended to every key
    :param cls:     Button class to use
    :returns:       A list of `cls` instances
    """
    return list([[cls( text=t
                     , callback_data=prefix + k
                     )
                 ] for k,t in choices])

choices = dict()


class TestHandler(telepot.aio.helper.ChatHandler):
    CHOICE = ( ('1', "Tomanten\n")
             , ('2', "Käse\n")
             , ('3', "Etwas anderes")
             , ('4', "noch mehr")
             , ('5', "nochviel mehr1")
             , ('6', "nochviel mehr2")
             , ('7', "nochviel mehr3")
             , ('8', "nochviel mehr4")
             , ('9', "nochviel mehr5")
             , ('10', "nochviel meh6r")
             , ('11', "nochviel mehr7")
             , ('12', "Andere auswahl")
             , ('13', "ZZZ")
             , ('14', "Bla")
             )
    def __init__(self, *args, **kwargs):
        super(TestHandler, self).__init__(*args, **kwargs)
        self._editor = None
        self._log = logging.getLogger('TestHandler')

    def _getInlineKeyboardChoice(self, choices):
        keyboard = kbchoice(choices)
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    def _getKeyboardChoice(self, choices):
        keyboard = [[KeyboardButton(text=v)] for k,v in choices]
        return ReplyKeyboardMarkup( keyboard = keyboard
                                  , selective = True
                                  )

    async def on_chat_message(self, msg):
        global choices
        content_type, chat_type, cid = glance(msg)
        if content_type != 'text':
            await self.sender.sendMessage("Unsupported content type: {}".format(content_type))
            return
        if msg['text'] == '/list':
            choices[cid] = list(self.CHOICE)
            self._log.debug("Add choices: {0}".format(choices))
            ed_obj = await self.sender.sendMessage \
                    ( 'Choose from list:'
                    , reply_markup = self._getInlineKeyboardChoice(choices[cid])
                    , parse_mode = "Markdown"
                    )
            kb_id = message_identifier(ed_obj)
            self._editor = telepot.aio.helper.Editor( self.bot
                                                    , kb_id
                                                    )
        else: # ignore
            await self.sender.sendMessage( "?? {text}".format(**msg)
                                         , reply_markup = ReplyKeyboardRemove()
                                         )

    async def on_callback_query(self, msg):
        global choices
        qid, from_id, key = glance(msg, flavor='callback_query')
        await self.bot.answerCallbackQuery(qid, text='Your choice: {}'.format(key))
        opts = choices.get(from_id, list())
        self._log.debug("Current choices for {0}: {1}".format(from_id, opts))
        self._log.debug("Shoud delete {0} for {1}".format(key, from_id))
        if len(opts) > 0:
            for i,p in enumerate(opts):
                if p[0] == key:
                    del choices[from_id][i]
                    self._log.debug("Delete key: {0}, index={1}".format(key, i))
                    break
            opts = choices[from_id]
            self._log.debug("After removal: {0}".format(opts))
        if self._editor is not None:
            if len(opts) > 0:
                self._log.debug("More options left...")
                await self._editor.editMessageReplyMarkup\
                        (reply_markup=self._getInlineKeyboardChoice(opts))
            else:
                self._log.debug("No more options")
                await self._editor.editMessageReplyMarkup(reply_markup=None)
                await self.sender.sendMessage("Done \U0001F600")
                self.close()

    def on_close(self, ex):
        self._log.debug("Closing TestHandler")


class ShoppingBot(telepot.aio.DelegatorBot):
    def __init__(self, token):
        self._log = logging.getLogger('ShoppingBot')
        super(ShoppingBot, self).__init__ \
                ( token
#                , [ ( per_chat_id()
#                    , call(self._send_welcome)
#                    )
#                  , pave_event_space()( per_chat_id()
                , [ include_callback_query_chat_id(pave_event_space())\
                         ( per_chat_id()
                         , create_open
                         , TestHandler
                         , timeout = 10
                         )
                , ]
                )

    async def _send_welcome(self, seed_tuple):
        chat_id = seed_tuple[1]['chat']['id']
        self._log.debug("Sending welcome message to {}".format(chat_id))
        msg = seed_tuple[1]
        usr_name = ( msg['chat'].get('first_name', str(chat_id))
                   + " "
                   + msg['chat'].get('last_name', '')
                   ).strip(" ")
        await self.sendMessage(chat_id, 'Welcome {}'.format(usr_name))

