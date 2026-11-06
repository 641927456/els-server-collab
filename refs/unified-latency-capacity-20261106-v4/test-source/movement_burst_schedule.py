"""Fixed QA: 5 moves/s; 10 moves/s during seconds30..40 of each minute."""
def schedule(seconds):
    assert type(seconds)is int and seconds>0
    result=[];ms=0
    while ms<seconds*1000:
        burst=30000<=ms%60000<40000
        result.append((ms/1000,burst));ms+=100 if burst else 200
    return tuple(result)
