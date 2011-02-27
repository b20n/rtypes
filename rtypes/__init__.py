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

    def __repr__(self):
        return "rlist(%s)" % str(self)

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
        if index == 0:
            instance.lpush(self.index, value)
        else:
            while True:
                try:
                    instance.watch(self.index)
                except redis.exceptions.ResponseError:
                    # Old, not thread-safe
                    # TODO: warn user?
                    pass
                post = instance.lrange(self.index, index, -1)
                pipe = instance.pipeline(transaction=True)
                pipe.ltrim(self.index, 0, index - 1)
                pipe.rpush(self.index, json.dumps(value))
                for value in post:
                    # Already serialized...
                    pipe.rpush(self.index, value)
                if pipe.execute():
                    break

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


class rdict:
    def __init__(self, *args, **kwargs):
        self.index = str(uuid.uuid4())
        self.update(*args, **kwargs)

    def __items__(self):
        # Helper for deserializing all entries
        maps = instance.hgetall(self.index)
        ret = {}
        for key in maps:
            ret[json.loads(key)] = json.loads(maps[key])
        return ret

    def __str__(self):
        # str(foo)
        return str(self.__items__())

    def __repr__(self):
        return "rdict(%s)" % str(self)

    def __len__(self):
        # len(foo)
        return instance.hlen(self.index)

    def __getitem__(self, key):
        # foo[key]
        val = instance.hget(self.index, json.dumps(key))
        if not val:
            raise KeyError
        return val

    def __setitem__(self, key, value):
        # foo[key] = value
        instance.hset(self.index, json.dumps(key), json.dumps(value))

    def __delitem__(self, key):
        # del foo[key]
        instance.hdel(self.index, json.dumps(key))

    def __contains__(self, key):
        # key in foo
        return instance.hexists(self.index, json.dumps(key))

    def __iter__(self):
        return self.Iterator(self)

    class Iterator:
        def __init__(self, rdict):
            # TODO: lazily load keys?
            self.index = 0
            self.keys = instance.hkeys(rdict.index)

        def next(self):
            if self.index < len(self.keys):
                self.index += 1
                return json.loads(self.keys[self.index - 1])
            else:
                raise StopIteration

    # API

    def clear(self):
        instance.delete(self.index)

    def copy(self):
        return self.__items__()

    def fromkeys(self, seq, value=None):
        # not implementing class methods
        raise NotImplemented

    def get(self, key, value=None):
        val = instance.hget(self.index, json.dumps(key))
        if not val:
            return value
        return json.loads(val)

    def has_key(self, key):
        return self.__contains__(key)

    def items(self):
        return [(key, self[key]) for key in self]

    def iteritems(self):
        raise NotImplemented

    def iterkeys(self):
        raise NotImplemented

    def itervalues(self):
        raise NotImplemented

    def keys(self):
        return [json.loads(key) for key in instance.hkeys(self.index)]

    def pop(self, key, **kwargs):
        val = instance.hget(self.index, json.dumps(key))
        if val is None:
            if "default" in kwargs:
                return kwargs["default"]
            else:
                raise KeyError
        else:
            return json.loads(val)

    def popitem(self):
        pair = instance.hgetall(self.index).popitem()
        instance.hdel(self.index, pair[0])
        return (json.loads(pair[0]), json.loads(pair[1]))

    def setdefault(self, key, default=None):
        val = instance.hget(self.index, json.dumps(key))
        if val is None:
            instance.hset(self.index, json.dumps(key), json.dumps(default))
            return default
        return json.loads(val)

    def update(self, *args, **kwargs):
        if kwargs:
            kvs = dict(kwargs)
        else:
            kvs = dict(args[0])
        for key in kvs:
            instance.hset(self.index,
                          json.dumps(key),
                          json.dumps(kvs[key]))

    def values(self):
        return [json.loads(val) for val in instance.hvals(self.index)]

    def viewitems(self):
        raise NotImplemented

    def viewkeys(self):
        raise NotImplemented

    def viewvalues(self):
        raise NotImplemented
