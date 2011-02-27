# rtypes - Redis-backed Python datastructures

rtypes provides Pythonic access to Redis datastructures. Currently, only the `list` and `dict` APIs are represented. All data is stored in Redis in JSON-serialized format, so don't try to store something that can't be serialized. Additionally, since the built-in `json` module is used, strings are stored as unicode.

Note that this project is something of a hack, and may make a mess if you actually try to use it.

## Dependencies

Python 2.6

[redis-py](https://github.com/andymccurdy/redis-py)

## Getting started

    import rtypes
    
    # Optionally, configure a Redis instance to use
    # Defaults to localhost:6379, db 0
    
    rtypes.configure(host=127.0.0.1, port=8008, db=16)
    
    foo = rtypes.rlist()
    foo.append(1)
    foo.extend([1, 2, 3])
    
    bar = rtypes.rdict(a=3, b=5, c=111)
    bar.keys()

### rtypes.rlist

`rtypes.rlist` provides functionality similar to that of Python's built-in `list` datastructure. `rlist.insert()` is not thread-safe if used with Redis versions that do not support the `WATCH` command.

### rtypes.rdict

`rtypes.rdict` provides functionality similar to that of Python's built-in `dict` datastructure. There are several omissions from the API, including generators and views.
