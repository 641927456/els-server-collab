# 副本里那个只有「确认」的空白弹窗（0x460）

## 症状

进副本后，屏幕中央周期性出现一个**没有任何正文**的白色确认框，只有一个「确认」按钮；
不点它也挡不住操作（角色还能跑、还能打）。实测每 30 秒来一次。

## 根因

客户端在副本里每 30 秒发一次 `0x460`（精华/材料操作）。服务端这条分支长这样：

```python
if self.item_test and self.client_build=='dx11_260923' and kind==0x460 and event.event_id==0x202:
    ...
    try:return essence_action(...)['events']
    except ValueError:return [essence_ack(result=-1)]
```

而 `boosting_2026_essence.request()` 认的形状是 **恰好 22 字节**：

```python
if not isinstance(payload,bytes) or len(payload)!=22:raise ValueError('Essence request size')
```

原生客户端实际发的是 **线包 96 字节**。线包与载荷的换算是固定的，`encode_frame(encode_event(...))`
跑一遍就知道 96 字节对应载荷 **25~32 字节**（25 和 32 都可能，取决于 padding）：

| 载荷 | 线包 |
| --- | --- |
| 22 | 88 |
| 25~32 | 96 |
| 34 | 104 |

也就是说这条请求**从来没有成功过**，每次都 `ValueError` → `essence_ack(result=-1)`。

`result=-1` 就是空白框的开关：**客户端错误表里没有 -1 对应的文案，取空文字**，
于是画出一个只有按钮的框。同一个坑在 `docs/NATIVE_MASTER_CURRENT_SKILLS_20261028.md`
记过一次（29F 自动入场返回 -1 时的中央白框），`docs/fixes/20261030-master-road-resurrection.md`
的复活白框也是同一机制。

## 修法

在拿到真实的 25~32 字节布局之前，先不弹框：拒绝时**不再回 -1**，回一个「无变化」的
原生应答（`essence_ack()` 默认 `result=0, changes=()`），并把这件的形状记在
`session.essence_rejection` 上：

```python
except ValueError as error:
    self.essence_rejection=(len(event.payload),str(error));return [essence_ack()]
```

同时给 `transport` 加了 `essence_diagnostic`，把这 30 秒一次的请求体原样打出来：

```json
{"event":"essence_diagnostic","sequence":1170,"size":26,"payload":"0000...","rejection":[26,"Essence request size"]}
```

下次进副本跑一会儿就能拿到真实字节，再按实际布局实现（当前只是止血，精华本身仍不可用）。

## 验证

- `tests/test_essence_request_shape.py`：22 字节才被接受、25/26/30/32 字节一律 `ValueError`、
  宽载荷的应答 result 必须是 **0**（不是 -1）且库存变更数为 0、离开副本阶段同样不弹框。
- 真机：重启启动器后进副本，空白框应消失；`server.jsonl` 里会出现 `essence_diagnostic`。

## 顺带记下

这条分支的门槛是 `self.item_test`，而 `config.py` 的 `session_options()` 给所有 integrated
会话都开了 `item_test=True`，所以这不是测试模式专属的坑，正常玩就会中。
