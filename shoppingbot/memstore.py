import logging


class MemoryStorage(object):

    def __init__(self):
        self._store = dict()

    def getList(self, cid):
        if cid in self._store:
            l = self._store[cid]
            return l
        else:
            return list()

    def enum(self, cid):
        if cid in self._store:
            return enumerate(l)

    def addItem(self, cid, item):
        if cid not in self._store:
            self._store[cid] = list()
        self._store[cid].append(item)

    def delItem(self, cid, index):
        if cid in self._store:
            try:
                del self._store[index]
                return True
            except IndexError:
                pass
        return False

    def dumpAll(self):
        logging.debug("Store content: {0!r}".format(self._store))
