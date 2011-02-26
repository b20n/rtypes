import redis
import uuid
import json

instance = redis.Redis()

def configure(host, port, db):
    global instance
    instance = redis.Redis(host=host, port=port, db=db)
    if not instance.ping():
        # TODO: different exception
        raise Exception
    return True

class rlist:
    def __init__(self, values=[]):
        self.index = str(uuid.uuid4())
        if values:
            for value in values:
                instance.rpush(self.index, json.dumps(value))

    def __str__(self):
        # str(foo)
        return str([json.loads(i) for i in instance.lrange(self.index, 0, -1)])

    def __len__(self):
        # len(foo)
        return instance.llen(self.index)

    def __getitem__(self, index):
        # foo[index]
        if not isinstance(index, slice):
            return json.loads(instance.lindex(self.index, index))
        else:
            start, stop, step = index.indices(len(self))
            pipe = instance.pipeline(transaction=True)
            while start < stop:
                pipe.lindex(self.index, start)
                start += step
            return [json.loads(i) for i in pipe.execute()]

    def __setitem__(self, index, value):
        # foo[index] = bar
        try:
            instance.lset(self.index, index, json.dumps(value))
        except redis.exceptions.ResponseError:
            # Key didn't exist yet, stick this in the end
            instance.rpush(self.index, json.dumps(value))

    def __delitem__(self, index):
        # del foo[index]
        pipe = instance.pipeline(transaction=True)
        pipe.lrange(self.index, 0, index - 1)
        pipe.lrange(self.index, index + 1, -1)
        pipe.delete(self.index)
        pre, post, _ = pipe.execute()
        # Already serialized...
        for value in pre:
            instance.rpush(self.index, value)
        for value in post:
            instance.rpush(self.index, value)

    def __iter__(self):
        return self.Iterator(self)

    class Iterator:
        def __init__(self, rlist):
            self.index = 0
            self.rlist = rlist

        def next(self):
            if self.index < len(self.rlist):
                self.index += 1
                return json.loads(instance.lindex(self.rlist.index,
                                                  self.index - 1))
            else:
                raise StopIteration

    # API

    def append(self, value):
        instance.rpush(self.index, json.dumps(value))

    def extend(self, iterable):
        pipe = instance.pipeline(transaction=True)
        for value in iterable:
            pipe.rpush(self.index, json.dumps(value))
        pipe.execute()

    def insert(self, index, value):
        # TODO: use linsert if we're 2.1.1+
        # Not thread-safe; we need WATCH, but if we're 2.1+, we'll have linsert
        post = instance.lrange(self.index, index, -1)
        pipe = instance.pipeline(transaction=True)
        pipe.ltrim(self.index, 0, index - 1)
        pipe.rpush(self.index, json.dumps(value))
        for value in post:
            # Already serialized...
            pipe.rpush(self.index, value)
        pipe.execute()

    def remove(self, value):
        for index, val in enumerate(self):
            if val == value:
                del self[index]
                break

    def pop(self, index=None):
        if index is None:
            return json.loads(instance.rpop(self.index))
        else:
            value = self[index]
            del self[index]

    def index(self, value):
        for index, val in enumerate(self):
            if val == value:
                return index

    def count(self, value):
        c = 0
        for val in self:
            if val == value:
                c += 1
        return c

    def sort(self):
        instance.sort(self.index, alpha=True, store=self.index)

    def reverse(self):
        tmp_index = str(uuid.uuid4())
        while True:
            tmp_val = instance.rpoplpush(self.index, tmp_index)
            if not tmp_val:
                break
        f.rename(tmp_index, self.index)
