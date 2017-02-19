import logging
import inspect
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
from .store import TinyStorage

store = TinyStorage('lists.json')


def get_chat_id(msg):
    return str(msg['chat']['id'])


class FlexibleIdleEventCoordinator(telepot.aio.helper.IdleEventCoordinator):
    def delay_once(self, timeout):
        try:
            if self._timeout_event:
                self._scheduler.cancel(self._timeout_event)
        except exception.EventNotFound:
            pass
        finally:
            self._timeout_event = self._scheduler.event_later \
                    ( timeout
                    , ( '_idle'
                      , {'seconds': timeout}
                      )
                    )


class Dialog(object):
    def __init__(self):
        methods = inspect.getmembers(self, inspect.ismethod)
        self._states = {k : v for k,v in methods if k.startswith('on_')}
        self._active = True
        self._state = self.on_start
        self.cid = None        # current chat id available in callback
        self.sender = None     # sender available in callback
        self.handler = None    # handler available in callback
        self.bot = None
        self.callback = False  # event triggerd from message-callback
        self.qid = None        # callback query id if callback is True (else None)

    def delay_once(self, timeout):
        try:
            self.handler._idle_event_coordinator.delay_once(timeout)
            logging.debug("Delaying timeout {0!r}: {1}".format( self.handler
                                                              ,timeout
                                                              ))
        except AttributeError:
            logging.debug("Delaying timeout is not supported by handler {0!r}".format(self.handler))

    def _getStateName(self, method):
        for k,v in self._states.items():
            if method == v:
                return k
        raise RuntimeError("State lookup for {:r} failed".format(method))

    def isActive(self):
        return self._active

    async def __call__(self, msg, handler, callback=False):
        if self._active:
            try:
                self.cid = get_chat_id(msg)
            except KeyError:
                logging.debug("Couldn't get cid; keep old {}".format(self.cid))
            self.handler = handler
            self.sender = handler.sender
            self.bot = handler.bot
            self.callback = callback
            if callback:
                self.qid = glance(msg, flavor='callback_query')[0]
            else:
                self.qid = None
            try:
                next = await self._state(msg)
            except Exception as e:
                import traceback
                logging.error("Dialog call failed: {}".format\
                        (traceback.format_exc()))
                next = None
            if next is None:
                logging.debug("Keep state {}".format(self._getStateName(self._state)))
            elif inspect.ismethod(next) and (next in self._states.values()):
                logging.debug("Switching dialog state {} -> {}".format\
                        ( self._getStateName(self._state)
                        , self._getStateName(next)
                        ))
                self._state = next
            elif next in self._states.keys():
                logging.debug("Switching dialog state {} -> {}".format\
                        ( self._getStateName(self._state)
                        , next
                        ))
                self._state = self._states[next]
            else:
                logging.warning("Illegal return from state {}: {}".format\
                        ( self._getStateName(self._state)
                        , next
                        ))
        else:
            logging.warning("Dialog is inactive")

    async def close(self, handler):
        if self._active:
            self._state = self.on_close
            await self(dict(), handler)
            self._active = False

    async def on_start(self, *args):
        pass

    async def on_close(self, *args):
        pass


class NullDialog(Dialog):
    def __init__(self):
        Dialog.__init__(self)
        self._active = False


class AddItemDialog(Dialog):
    ADD_TIMEOUT = 60 * 5

    def __init__(self):
        Dialog.__init__(self)
        self._count = 0

    async def on_start(self, msg):
        self._count = 0
        self.delay_once(self.ADD_TIMEOUT)
        await self.sender.sendMessage("Plase name items to put on the list:")
        return self.on_add

    async def on_add(self, msg):
        global store
        store.addItem(self.cid, msg['text'])
        self._count += 1
        self.delay_once(self.ADD_TIMEOUT)
        await self.sender.sendMessage("Added item {text}".format(**msg))

    async def on_close(self, *args):
        if self._count > 0:
            await self.sender.sendMessage("Added {} items\U0001F600".format\
                            (self._count))


class ShoppingDialog(Dialog):
    SHOP_TIMEOUT = 60*60 * 2  # 2 hours
    def __init__(self):
        Dialog.__init__(self)
        self._editor = None

    def _prepare_kb(self):
        global store
        cls = InlineKeyboardButton
        ikb = list([[cls(text=v, callback_data=str(k))
                     for k,v in store.enum(self.cid)
                  ]])
        if ikb:
            return InlineKeyboardMarkup(inline_keyboard=ikb)
        else:
            return None

    async def on_start(self, msg):
        kb = self._prepare_kb()
        if kb is None:
            await self.sender.sendMessage \
                    ( "Your shopping list is already empty"
                    , reply_markup = None
                    )
            self._editor = None
            await self.close()
            return None
        self.delay_once(self.SHOP_TIMEOUT)
        ed_obj = await self.sender.sendMessage \
                ( "Your list"
                , reply_markup = kb
                )
        kb_id = message_identifier(ed_obj)
        self._editor = telepot.aio.helper.Editor( self.bot
                                                , kb_id
                                                )
        return self.on_select

    async def on_select(self, msg):
        global store
        if not self.callback:
            logging.error("ignoring message {0!r}".format(msg))
            return None
        qid, from_id, key = glance(msg, flavor='callback_query')
        logging.debug("delete key={0}".format(key))
        ret, r = store.delItem(self.cid, key)
        self.delay_once(self.SHOP_TIMEOUT)
        if r is not None:
            await self.bot.answerCallbackQuery \
                    ( qid
                    , text = "Ticked off {}".format(r['item'])
                    )
        kb = self._prepare_kb()
        await self._editor.editMessageReplyMarkup(reply_markup=kb)
        if kb is None:
            await self.sender.sendMessage("Done \U0001F600")

    async def on_close(self, *args):
        if self._editor is not None:
            await self._editor.editMessageReplyMarkup(reply_markup=None)


class TestHandler(telepot.aio.helper.ChatHandler):
    IdleEventCoordinator = FlexibleIdleEventCoordinator

    def __init__(self, *args, **kwargs):
        super(TestHandler, self).__init__(*args, **kwargs)
        self._editor = None
        self._log = logging.getLogger('TestHandler')
        self._dialog = NullDialog()

    async def _sendList(self, msg):
        global store
        try:
            cid = get_chat_id(msg)
        except KeyError:
            logging.error("Request seems wrong: {0!r}".format(msg))
            return
        store.dumpAll()
        l = store.getList(cid)
        if l:
            fmt_l = "\n".join(["- {}".format(i) for i in l])
            await self.sender.sendMessage \
                    ("Your shopping list:\n\n{}".format(fmt_l))
        else:
            await self.sender.sendMessage("Your shopping list is empty \U0001F600")

    async def on_chat_message(self, msg):
        content_type, chat_type, cid = glance(msg)
        logging.debug("on_chat_message: {0!s}".format(msg))
        if content_type == 'new_chat_member':
            return  # ignore
        if content_type != 'text':
            await self.sender.sendMessage("Unsupported content type: {}".format(content_type))
            return
        if msg['text'].startswith('/'):  # command
            await self._dialog.close(self)
            self._dialog = NullDialog()
            if msg['text'] == '/cancel':
                pass
            elif msg['text'] == '/list':
                await self._sendList(msg)
            elif msg['text'] == '/multiadd':
                self._dialog = AddItemDialog()
                await self._dialog(msg, self)
            elif msg['text'] == '/shop':
                self._dialog = ShoppingDialog()
                await self._dialog(msg, self)
            else:
                logging.error("Unkown command (ignoring): {text}".format(**msg))
        elif self._dialog.isActive():
            await self._dialog(msg, self)
        else: # ignore
            logging.warning("Bot ignores message: {text}".format(**msg))

    async def on_callback_query(self, msg):
        qid, from_id, key = glance(msg, flavor='callback_query')
        logging.debug("on_callback_query: {0!s}".format(msg))
        if self._dialog.isActive():
            await self._dialog(msg, self, callback=True)

    async def on_close(self, ex):
        self._log.debug("Closing TestHandler ...")
        await self._dialog.close(self)


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
                         , timeout = 5
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

