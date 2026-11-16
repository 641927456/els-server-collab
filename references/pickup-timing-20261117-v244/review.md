仅3个服务端叶：hunter_chest.py、fishing_bait_loot.py、pve_economy_flow.py。前两项保持完整before验证和after审计，只重读工厂改变UID；鱼饵复用既有FIFO。第三项仅固定类别计时，移除包装后业务AST等价。复用12+14+9项组件结果，计时边界另审。保留所有V243既有字节和玩家数据，未启动客户端。
