"""Keep shared writer exceptions separate from their callers' tracebacks."""


def caller_error(error):
    result=type(error)(*error.args)
    for name in('sqlite_errorcode','sqlite_errorname'):
        if hasattr(error,name):setattr(result,name,getattr(error,name))
    return result


def writer_result(future):
    # exception() waits without raising the shared object through this
    # caller's stack (whose f_back chain would retain the actor).
    error=future.exception()
    if error is not None:raise caller_error(error) from error
    return future.result()
