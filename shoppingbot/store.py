import logging
from tinydb import TinyDB, Query


class TinyStorage(object):
    def __init__(self, path=None):
        if path is None:
            path = "tinydb.json"
        self._db = db = TinyDB(path)
        logging.debug("Load DB {}".format(path))

    def getList(self, cid):
        return list([v for k,v in self.enum(cid)])

    def _get_entry(self, cid):
        if not isinstance(cid, str):
            raise TypeError("'cid' has invalid type '{0!s}'".format(type(cid)))
        r = self._db.search( (Query().cid == cid)
                           & (Query().item.exists())
                           )
        return r

    def enum(self, cid):
        r = self._get_entry(cid)
        return [(i.eid, i['item']) for i in r]

    def addItem(self, cid, item):
        self._db.insert(dict(cid=cid, item=item))

    def delItem(self, cid, eid):
        r = self._db.get(eid=eid)
        if r is not None:
            try:
                if r['cid'] == cid:
                    self._db.remove(eids=[eid])
                    logging.debug("Remove Item {0!s}".format(r))
                else:
                    logging.error("Remove not allowed: cid={0}, r={1!s}".format\
                            (cid, r))
                    return False, None
            except (KeyError, IndexError):
                logging.debug("Element {0} already removed".format(eid))
        return True, r

    def dumpAll(self):
        logging.debug("Store content: {0!r}".format(self._db.all()))
