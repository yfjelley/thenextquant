## 交易

通过交易模块(trade)，可以在任意交易平台发起交易，包括下单(create_order)、撤单(revoke_order)、查询订单状态(order status)、
查询未完全成交订单(get_open_order_nos)等功能；

策略完成下单之后，底层框架将定时或实时将最新的订单状态更新通过策略注册的回调函数传递给策略，策略能够在第一时间感知到订单状态更新数据；


### 交易模块使用

> 此处以在 `Binance` 交易所上的 `ETH/BTC` 交易对创建一个买单为例
```python
# 导入模块
from quant import const
from quant import order
from quant.trade import Trade
from quant.utils import logger

# 初始化
platform = const.BINANCE  # 交易平台 假设是binance
account = "abc@gmail.com"  # 交易账户
access_key = "ABC123"  # API KEY
secret_key = "abc123"  # SECRET KEY
symbol = "ETH/BTC"  # 交易对
strategy_name = "my_test_strategy"  # 自定义的策略名称

# 注册订单更新回调函数，注意此处注册的回调函数是 `async` 异步函数，回调参数为 `order` 对象，数据结构请查看下边的介绍。
async def on_event_order_update(order):
    logger.info("order:", order)

# 创建trade对象
trader = Trade(strategy_name, platform, symbol, account=account, access_key=access_key, secret_key=secret_key, 
                order_update_callback=on_event_order_update)

# 下单
action = order.ORDER_ACTION_BUY  # 买单
price = "11.11"  # 委托价格
quantity = "22.22"  # 委托数量
order_type = order.ORDER_TYPE_LIMIT  # 限价单
order_no, error = await trader.create_order(action, price, quantity, order_type)  # 注意，此函数需要在 `async` 异步函数里执行


# 撤单
order_no, error = await trader.revoke_order(order_no)  # 注意，此函数需要在 `async` 异步函数里执行


# 查询所有未成交订单id列表
order_nos, error = await trader.get_open_order_nos()  # 注意，此函数需要在 `async` 异步函数里执行


# 查询当前所有未成交订单数据
orders = trader.orders  # orders是一个dict，key为order_no，value为order对象
order = trader.orders.get(order_no)  # 提取订单号为 order_no 的订单对象
```

### 订单对象模块

所有订单相关的数据常量和对象在框架的 `quant.order` 模块下。

- 订单类型
```python
from quant import order

order.ORDER_TYPE_LIMIT  # 限价单
order.ORDER_TYPE_MARKET  # 市价单
```

- 订单操作
```python
from quant import order

order.ORDER_ACTION_BUY  # 买入
order.ORDER_ACTION_SELL  # 卖出
```

- 订单状态
```python
from quant import order

order.ORDER_STATUS_NONE = "NONE"  # 新创建的订单，无状态
order.ORDER_STATUS_SUBMITTED = "SUBMITTED"  # 已提交
order.ORDER_STATUS_PARTIAL_FILLED = "PARTIAL-FILLED"  # 部分处理
order.ORDER_STATUS_FILLED = "FILLED"  # 处理
order.ORDER_STATUS_CANCELED = "CANCELED"  # 取消
order.ORDER_STATUS_FAILED = "FAILED"  # 失败订单
```

- 订单对象
```python
from quant import order

o = order.Order()
o.platform  # 交易平台
o.account  # 交易账户
o.strategy  # 策略名称
o.order_no  # 委托单号
o.action  # 买卖类型 SELL-卖，BUY-买
o.order_type  # 委托单类型 MKT-市价，LMT-限价
o.symbol  # 交易对 如: ETH/BTC
o.price  # 委托价格
o.quantity  # 委托数量（限价单）
o.remain  # 剩余未成交数量
o.status  # 委托单状态
o.timestamp  # 创建订单时间戳(毫秒)
o.avg_price  # 成交均价
o.trade_type  # 合约订单类型 开多/开空/平多/平空
o.ctime  # 创建订单时间戳
o.utime  # 交易所订单更新时间
```
