import power_fixture

def enroll(row,index,path,operation):
    return power_fixture.enroll(row,index,path,operation)

def cold(rows,path,*,retired=False):
    return dict(ok=True,read_only=True,retired=retired,cases=[power_fixture.cold(row,path,retired=retired)for row in rows])
