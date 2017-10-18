import logging
from tinydb import TinyDB, Query


class TinyStorage(object):
    def __init__(self, path=None):
        if path is None:
            path = "tinydb.json"
        self._db = db = TinyDB(path)
        logging.debug("Load DB {}".format(path))

    def getList(self, cid, checked=False):
        return list([v for k,v in self.enum(cid, checked=checked)])

    def getCheckList(self, cid):
        if not isinstance(cid, str):
            raise TypeError("'cid' has invalid type '{0!s}'".format(type(cid)))
        query = (Query().cid == cid) & (Query().item.exists())
        for i in self._db.search(query):
            if i.get('checked', 0) == 1:
                yield (i.eid, i['item'], True)
            else:
                yield (i.eid, i['item'], False)

    def _get_entry(self, cid, checked=False):
        if not isinstance(cid, str):
            raise TypeError("'cid' has invalid type '{0!s}'".format(type(cid)))
        if checked:
            qck = (Query().checked == 1)
        else:
            qck = ~(Query().checked.exists())
        r = self._db.search( (Query().cid == cid)
                           & (Query().item.exists())
                           & qck
                           )
        return r

    def enum(self, cid, checked=False):
        r = self._get_entry(cid, checked=checked)
        return [(i.eid, i['item']) for i in r]

    def swapItems(self, cid, eid_a, eid_b):
        eid_a = int(eid_a)
        eid_b = int(eid_b)
        a = self._db.get(eid=eid_a)
        b = self._db.get(eid=eid_b)
        if (a['cid'] != cid) or (b['cid'] != cid):
            raise RuntimeError("Invalid items selected")
        logging.debug("A: {0}".format(a))
        logging.debug("B: {0}".format(b))
        # HACK: override old item to 'fake' swapping
        self._db.update(a, eids=[eid_b])
        self._db.update(b, eids=[eid_a])

    def addItem(self, cid, item):
        self._db.insert(dict(cid=cid, item=item))

    def checkItem(self, cid, eid):
        eid = int(eid)
        r = self._db.get(eid=eid)
        logging.debug("Get key: {0!s}".format(r))
        if r is not None:
            try:
                if r['cid'] == cid:
                    self._db.update(dict(checked=1), eids=[eid])
                    logging.debug("Check Item {0!s}".format(r))
                else:
                    logging.error("Check not allowed: cid={0}, r={1!s}".format\
                            (cid, r))
                    return False, None
            except (KeyError, IndexError):
                logging.debug("Element {0} already removed".format(eid))
        return True, r

    def removeChecked(self, cid):
        self._db.remove( (Query().cid == cid)
                       & (Query().checked == 1)
                       )

    def dumpAll(self):
        l = [(i.eid, i) for i in self._db.all()]
        logging.debug("Store content: {0!s}".format(l))
