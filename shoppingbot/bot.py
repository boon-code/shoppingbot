import logging
import asyncio
import telepot
from telepot import glance, message_identifier
from telepot.namedtuple import ( InlineKeyboardMarkup
                               , InlineKeyboardButton
                               )
from telepot.aio.delegate import ( pave_event_space
                                 , per_chat_id
                                 , create_open
                                 , call
                                 , include_callback_query_chat_id
                                 )

def kbchoice(choices, prefix=''):
    """ Generates keyboard buttons

    :param choices: a list of tuples to generate keyboard buttons from. First
                    item of each tuple in the list is a key (for processing),
                    second item is the text to display
    :param prefix:  optional prefix which will be prepended to every key
    :returns:       A list of InlineKeyboardButtons
    """
    return list([InlineKeyboardButton( text=t
                                     , callback_data=prefix + k
                                     ) for k,t in choices])


class TestHandler(telepot.aio.helper.ChatHandler):
    CHOICE = ( ('1', "Tomanten")
             , ('2', "Käse")
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

    def _getKeyboardChoice(self):
        keyboard = [kbchoice(self.CHOICE, prefix='opt')]
        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    async def on_chat_message(self, msg):
        content_type, chat_type, cid = glance(msg)
        if content_type != 'text':
            await self.sender.sendMessage("Unsupported content type: {}".format(content_type))
            return
        if msg['text'] == '/list':
            ed_obj = await self.sender.sendMessage \
                    ( 'Choose from list:'
                    , reply_markup = self._getKeyboardChoice()
                    )
            kb_id = message_identifier(ed_obj)
            self._editor = telepot.aio.helper.Editor( self.bot
                                                    , kb_id
                                                    )
        else: # ignore
            return

    async def on_callback_query(self, msg):
        cid, from_id, key = glance(msg, flavor='callback_query')
        await self.bot.answerCallbackQuery(cid, text='Your choice: {}'.format(key))
        if self._editor is not None:
            await self._editor.editMessageReplyMarkup(reply_markup=None)
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

