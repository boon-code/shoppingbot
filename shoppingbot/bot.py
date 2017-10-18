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
    if 'chat' in msg:
        return str(msg['chat']['id'])
    elif 'message' in msg:
        return str(msg['message']['chat']['id'])
    else:
        raise KeyError("Missing chat id")


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
        self.query_id = None   # callback query id if callback is True (else None)
        self.query_key = None  # callback query data if callback is True (else None)

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
                self.query_id, _, self.query_key = glance(msg, flavor='callback_query')
            else:
                self.query_id = None
                self.query_key = None
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
        await self.sender.sendMessage("Please name items to put on the list:")
        return self.on_add

    async def on_add(self, msg):
        global store
        store.addItem(self.cid, msg['text'])
        self._count += 1
        self.delay_once(self.ADD_TIMEOUT)
        await self.sender.sendMessage("Added item {text}".format(**msg))

    async def on_close(self, *args):
        if self._count > 0:
            text = 'item'
            if self._count > 1:
                text = 'items'
            await self.sender.sendMessage("Added {} {} \U0001F600".format\
                            (self._count, text))


class ShoppingDialog(Dialog):
    SHOP_TIMEOUT = 60*60 * 2  # 2 hours
    def __init__(self):
        Dialog.__init__(self)
        self._editor = None

    def _prepare_kb(self):
        global store
        cls = InlineKeyboardButton
        ikb = list([[cls(text=v, callback_data=str(k))]
                     for k,v in store.enum(self.cid)
                  ])
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
            await self.close(self.handler)
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
        logging.debug("delete key={0}".format(self.query_key))
        ret, r = store.checkItem(self.cid, self.query_key)
        self.delay_once(self.SHOP_TIMEOUT)
        if r is not None:
            await self.bot.answerCallbackQuery \
                    ( self.query_id
                    , text = "Ticked off {}".format(r['item'])
                    )
        if r.get('checked', 0) == 1:
            logging.debug("Item was already checked -> ignoring")
        else:  # wasn't already checked
            kb = self._prepare_kb()
            await self._editor.editMessageReplyMarkup(reply_markup=kb)
            if kb is None:
                chk_list = [ "- {0}".format(i) for i in store.getList(self.cid, checked=True)]
                txt = "Shopping list done\n\n{0}".format("\n".join(chk_list))
                store.removeChecked(self.cid)
                await self._editor.editMessageText(text=txt)
                self._editor = None
                await self.close(self.handler)
        return None

    async def on_close(self, *args):
        if self._editor is not None:
            await self._editor.editMessageReplyMarkup(reply_markup=None)


class SwapDialog(Dialog):
    SWAP_TIMEOUT = 5 * 60
    def __init__(self):
        Dialog.__init__(self)
        self._editor = None
        self._key = [None, None]

    def _prepare_kb(self, exclude=tuple()):
        global store
        cls = InlineKeyboardButton
        ikb = list()
        for k,v in store.enum(self.cid):
            if k not in exclude:
                ikb.append([cls(text=v, callback_data=str(k))])
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
            await self.close(self.handler)
            return None
        self.delay_once(self.SWAP_TIMEOUT)
        ed_obj = await self.sender.sendMessage \
                ( "Your list to swap"
                , reply_markup = kb
                )
        kb_id = message_identifier(ed_obj)
        self._editor = telepot.aio.helper.Editor( self.bot
                                                , kb_id
                                                )
        return self.on_select_1

    async def on_select_1(self, msg):
        global store
        if not self.callback:
            logging.error("ignoring message {0!r}".format(msg))
            return None
        self.delay_once(self.SWAP_TIMEOUT)
        logging.debug("select first: {0}".format(self.query_key))
        self._key[0] = int(self.query_key)
        await self.bot.answerCallbackQuery \
                ( self.query_id
                , text = "Select {0}".format(self._key[0])
                )
        kb = self._prepare_kb(exclude=(self._key[0],))
        logging.debug("kb: {0}".format(kb))
        await self._editor.editMessageReplyMarkup(reply_markup=kb)
        return self.on_select_2

    async def on_select_2(self, msg):
        global store
        if not self.callback:
            logging.error("ignoring message {0!r}".format(msg))
            return None
        self.delay_once(self.SWAP_TIMEOUT)
        logging.debug("select second: {0}".format(self.query_key))
        self._key[1] = int(self.query_key)
        if (self._key[0] == self._key[1]) or (None in self._key):
            await self.bot.answerCallbackQuery \
                    ( self.query_id
                    , text = "Abort swap command"
                    )
        else:
            logging.debug("Swapping {0} and {1}".format(*self._key))
            await self.bot.answerCallbackQuery \
                    ( self.query_id
                    , text = "Swap {0} and {1}".format(*self._key)
                    )
        store.swapItems(self.cid, self._key[0], self._key[1])
        kb = self._prepare_kb()
        await self._editor.editMessageReplyMarkup(reply_markup=kb)
        return self.on_select_1


class CommandCollection(object):
    def __init__(self):
        self._cmds = dict()

    def addSimple(self, cmd, func, help="", prio=0):
        self._cmds["/{}".format(cmd)] = dict\
                ( func = func
                , cmd = cmd
                , help = help
                , type = 'function'
                , priority = prio
                )
    def addDialog(self, cmd, dialog_cls, help="", prio=0):
        self._cmds["/{}".format(cmd)] = dict\
                ( dialog = dialog_cls
                , cmd = cmd
                , help = help
                , type = 'dialog'
                , priority = prio
                )
    def addNoOperation(self, cmd, help="", prio=0):
        self._cmds["/{}".format(cmd)] = dict\
                ( cmd = cmd
                , help = help
                , type = 'nop'
                , priority = prio
                )

    def _msgToCommand(self, msg, botname=None):
        cmdtext = msg['text']
        tmp = cmdtext.split('@', 1)
        if len(tmp) > 1:
            if botname is not None:
                if botname != tmp[1]:
                    return None
            else:
                logging.warning("Not checking botname: {0}".format(cmdtext))
        return self._cmds.get(tmp[0], None)

    def isCommand(self, msg, botname=None):
        return self._msgToCommand(msg, botname=botname) is not None

    def _sort_func(self, cmd_obj):
        return (-cmd_obj.get('priority', 0), cmd_obj.get('cmd', ''))

    def _sorted(self):
        return [i for i in sorted(self._cmds.values(), key=self._sort_func)]

    def helpText(self, first_line):
        l = ["/{0} - {1}".format(i['cmd'], i['help']) for i in self._sorted()]
        return "{0}\n\n{1}".format( first_line
                                  , "\n".join(l)
                                  )

    def commandList(self):
        l = ["{0} - {1}".format(i['cmd'], i['help']) for i in self._sorted()]
        return "\n".join(l)

    def commands(self):
        return self._cmds

    def get(self, msg, botname=None):
        return self._msgToCommand(msg, botname=botname)


class TestHandler(telepot.aio.helper.ChatHandler):
    IdleEventCoordinator = FlexibleIdleEventCoordinator

    def __init__(self, *args, **kwargs):
        super(TestHandler, self).__init__(*args, **kwargs)
        self._editor = None
        self._log = logging.getLogger('TestHandler')
        self._dialog = NullDialog()
        cc = CommandCollection()
        cc.addSimple( 'list'
                    , self._sendList
                    , prio = 1
                    , help = "Show current shopping list"
                    )
        cc.addDialog( 'multiadd'
                    , AddItemDialog
                    , prio = 2
                    , help = "Add multiple items to list"
                    )
        cc.addDialog( 'shop'
                    , ShoppingDialog
                    , prio = 2
                    , help = "Start shopping"
                    )
        cc.addNoOperation( 'cancel'
                         , prio = 1
                         , help = "Cancel current operation"
                         )
        cc.addDialog( 'swap'
                    , SwapDialog
                    , prio = 1
                    , help = "Swap items on list"
                    )
        cc.addSimple( 'cleanup'
                    , self._cleanupList
                    , help = "Remove checked items from list"
                    )
        cc.addSimple( 'help'
                    , self._sendHelp
                    , help = "Show help text"
                    )
        cc.addSimple( 'cmd'
                    , self._sendCommandList
                    , help = "Show command list"
                    )
        self._cc = cc

    def _format_checklist(self, chklst):
        for id,txt,checked in sorted(chklst, key=lambda x: x[0]):
            if checked:
                yield " - [x] {0}".format(txt)
            else:
                yield " - [ ] {0}".format(txt)

    async def _sendList(self, msg):
        global store
        try:
            cid = get_chat_id(msg)
        except KeyError:
            logging.exception("Request seems wrong: {0!r}".format(msg))
            return
        store.dumpAll()
        l = list(self._format_checklist(store.getCheckList(cid)))
        if l:
            await self.sender.sendMessage \
                    ("Your shopping list:\n\n{}".format("\n".join(l)))
        else:
            await self.sender.sendMessage("Your shopping list is empty \U0001F600")

    async def _cleanupList(self, msg):
        global store
        try:
            cid = get_chat_id(msg)
        except KeyError:
            logging.exception("Request seems wrong: {0!r}".format(msg))
            return
        store.removeChecked(cid)
        await self.sender.sendMessage \
                ("Cleaned up your shopping list")

    async def _sendHelp(self, msg):
        logging.debug("Bot: {0!r}".format(dir(self.bot)))
        me = await self.bot.getMe()
        logging.debug("Bot: {0!r}".format(me))
        await self.sender.sendMessage(self._cc.helpText("Shopping List Bot"))

    async def _sendCommandList(self, msg):
        await self.sender.sendMessage(self._cc.commandList())

    async def on_chat_message(self, msg):
        content_type, chat_type, cid = glance(msg)
        logging.debug("on_chat_message: {0!s}".format(msg))
        if content_type == 'new_chat_member':
            return  # ignore
        if content_type != 'text':
            await self.sender.sendMessage("Unsupported content type: {}".format(content_type))
            return
        if msg['text'].startswith('/'):
            botname = await self.bot.getBotName()
            cmd = self._cc.get(msg, botname=botname)
            if cmd is not None:
                await self._dialog.close(self)
                cmd = self._cc.get(msg)
                if cmd['type'] == 'function':
                    self._dialog = NullDialog()
                    await cmd['func'](msg)
                elif cmd['type'] == 'dialog':
                    self._dialog = cmd['dialog']()
                    await self._dialog(msg, self)
                elif cmd['type'] == 'nop':
                    self._dialog = NullDialog()
                else:
                    logging.error("Unexpected command type {type}".format(**cmd))
            else:
                logging.debug("Ignoring unknown command {0!s}".format(msg))
        elif self._dialog.isActive():
            await self._dialog(msg, self)
        else: # ignore
            logging.warning("Bot ignores message: {text}".format(**msg))

    async def on_callback_query(self, msg):
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
        self._botname = None

    async def getBotName(self):
        if self._botname is None:
            user = await self.getMe()
            self._botname = user['username']
        return self._botname

    async def _send_welcome(self, seed_tuple):
        chat_id = seed_tuple[1]['chat']['id']
        self._log.debug("Sending welcome message to {}".format(chat_id))
        msg = seed_tuple[1]
        usr_name = ( msg['chat'].get('first_name', str(chat_id))
                   + " "
                   + msg['chat'].get('last_name', '')
                   ).strip(" ")
        await self.sendMessage(chat_id, 'Welcome {}'.format(usr_name))

