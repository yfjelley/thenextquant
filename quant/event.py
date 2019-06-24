# -*— coding:utf-8 -*-

"""
事件处理中心

Author: HuangTao
Date:   2018/05/04
Update: 2018/09/26  1. 优化回调函数由exchange和routing_key确定；
        2018/11/23  1. 事件增加批量订阅消息类型；
        2018/11/28  1. 增加断线重连机制；
"""

import json
import zlib
import asyncio

import aioamqp

from quant import const
from quant.utils import logger
from quant.config import config
from quant.tasks import LoopRunTask, SingleTask
from quant.utils.decorator import async_method_locker
from quant.market import Orderbook, Trade, Kline
from quant.asset import Asset


__all__ = ("EventCenter", "EventConfig", "EventHeartbeat", "EventAsset", "EventOrder", "EventKline", "EventOrderbook",
           "EventTrade")


class Event:
    """ 事件
    """

    def __init__(self, name=None, exchange=None, queue=None, routing_key=None, pre_fetch_count=1, data=None):
        """ 初始化
        @param name 事件名
        @param exchange 事件被投放的RabbitMQ交换机
        @param queue 事件被路由的RabbitMQ队列
        @param routing_key 路由规则
        @param pre_fetch_count 每次从消息队列里获取处理的消息条数，越多处理效率越高，但同时消耗内存越大，对进程压力也越大
        @param data 待发布事件的数据
        """
        self._name = name
        self._exchange = exchange
        self._queue = queue
        self._routing_key = routing_key
        self._pre_fetch_count = pre_fetch_count
        self._data = data
        self._callback = None  # 事件回调函数

    @property
    def name(self):
        return self._name

    @property
    def exchange(self):
        return self._exchange

    @property
    def queue(self):
        return self._queue

    @property
    def routing_key(self):
        return self._routing_key

    @property
    def prefetch_count(self):
        return self._pre_fetch_count

    @property
    def data(self):
        return self._data

    def dumps(self):
        """ 导出Json格式的数据
        """
        d = {
            "n": self.name,
            "d": self.data
        }
        s = json.dumps(d)
        b = zlib.compress(s.encode("utf8"))
        return b

    def loads(self, b):
        """ 加载Json格式的bytes数据
        @param b bytes类型的数据
        """
        b = zlib.decompress(b)
        d = json.loads(b.decode("utf8"))
        self._name = d.get("n")
        self._data = d.get("d")
        return d

    def parse(self):
        """ 解析self._data数据
        """
        raise NotImplemented

    def subscribe(self, callback, multi=False):
        """ 订阅此事件
        @param callback 回调函数
        @param multi 是否批量订阅消息，即routing_key为批量匹配
        """
        from quant.quant import quant
        self._callback = callback
        SingleTask.run(quant.event_center.subscribe, self, self.callback, multi)

    def publish(self):
        """ 发布此事件
        """
        from quant.quant import quant
        SingleTask.run(quant.event_center.publish, self)

    async def callback(self, exchange, routing_key, body):
        """ 事件回调
        @param exchange 事件被投放的RabbitMQ交换机
        @param routing_key 路由规则
        @param body 从RabbitMQ接收到的bytes类型数据
        """
        self._exchange = exchange
        self._routing_key = routing_key
        self.loads(body)
        o = self.parse()
        await self._callback(o)

    def __str__(self):
        info = "EVENT: name={n}, exchange={e}, queue={q}, routing_key={r}, data={d}".format(
            e=self.exchange, q=self.queue, r=self.routing_key, n=self.name, d=self.data)
        return info

    def __repr__(self):
        return str(self)


class EventConfig(Event):
    """ 配置更新事件
    * NOTE:
        发布：管理工具
        订阅：配置模块
    """

    def __init__(self, server_id=None, params=None):
        """ 初始化
        """
        name = "EVENT_CONFIG"
        exchange = "Config"
        queue = "{server_id}.{exchange}".format(server_id=server_id, exchange=exchange)
        routing_key = "{server_id}".format(server_id=server_id)
        data = {
            "server_id": server_id,
            "params": params
        }
        super(EventConfig, self).__init__(name, exchange, queue, routing_key, data=data)

    def parse(self):
        """ 解析self._data数据
        """
        pass


class EventHeartbeat(Event):
    """ 服务心跳事件
    * NOTE:
        订阅：监控模块
        发布：所有服务
    """

    def __init__(self, server_id=None, count=None):
        """ 初始化
        @param server_id 服务进程id
        @param count 心跳次数
        """
        name = "EVENT_HEARTBEAT"
        exchange = "Heartbeat"
        queue = "{server_id}.{exchange}".format(server_id=server_id, exchange=exchange)
        data = {
            "server_id": server_id,
            "count": count
        }
        super(EventHeartbeat, self).__init__(name, exchange, queue, data=data)

    def parse(self):
        """ 解析self._data数据
        """
        pass


class EventAsset(Event):
    """ 资产更新事件
    * NOTE:
        发布：资产服务
        订阅：业务模块
    """

    def __init__(self, platform=None, account=None, assets=None, timestamp=None, update=False):
        """ 初始化
        @param platform 交易平台
        @param account 交易账户
        @param assets 资产信息 {"BTC": {"free": "1.1", "locked": "2.2", "total": "3.3"}, ... }
        @param timestamp 时间戳(毫秒)
        @param update 资产是否更新 True 有更新 / False 无更新
        """
        name = "EVENT_ASSET"
        exchange = "Asset"
        routing_key = "{platform}.{account}".format(platform=platform, account=account)
        queue = "{server_id}.{exchange}.{routing_key}".format(server_id=config.server_id,
                                                              exchange=exchange,
                                                              routing_key=routing_key)
        data = {
            "platform": platform,
            "account": account,
            "assets": assets,
            "timestamp": timestamp,
            "update": update
        }
        super(EventAsset, self).__init__(name, exchange, queue, routing_key, data=data)

    def parse(self):
        """ 解析self._data数据
        """
        asset = Asset(**self.data)
        return asset


class EventOrder(Event):
    """ 委托单事件
    * NOTE:
        发布：策略服务
        订阅：业务服务
    """

    def __init__(self, platform=None, account=None, strategy=None, order_no=None, symbol=None, action=None, price=None,
                 quantity=None, status=None, order_type=None, timestamp=None):
        """ 初始化
        @param platform 交易平台名称
        @param account 交易账户
        @param strategy 策略名
        @param order_no 订单号
        @param symbol 交易对
        @param action 操作类型
        @param price 限价单价格
        @param quantity 限价单数量
        @param status 订单状态
        @param order_type 订单类型
        @param timestamp 时间戳(毫秒)
        """
        name = "EVENT_ORDER"
        exchange = "Order"
        routing_key = "{platform}.{account}.{symbol}".format(platform=platform, account=account, symbol=symbol)
        queue = "{server_id}.{exchange}.{routing_key}".format(server_id=config.server_id,
                                                              exchange=exchange,
                                                              routing_key=routing_key)
        data = {
            "platform": platform,
            "account": account,
            "strategy": strategy,
            "order_no": order_no,
            "symbol": symbol,
            "action": action,
            "price": price,
            "quantity": quantity,
            "status": status,
            "order_type": order_type,
            "timestamp": timestamp
        }
        super(EventOrder, self).__init__(name, exchange, queue, routing_key, data=data)

    def parse(self):
        """ 解析self._data数据
        """
        pass


class EventKline(Event):
    """ K线更新事件 1分钟，5分钟，15分钟
    * NOTE:
        发布：行情服务
        订阅：业务服务
    """

    def __init__(self, platform=None, symbol=None, open=None, high=None, low=None, close=None, volume=None,
                 timestamp=None, kline_type=None):
        """ 初始化
        @param platform 平台
        @param symbol 交易对
        @param open 开盘价
        @param high 最高价
        @param low 最低价
        @param close 收盘价
        @param volume 成交量
        @param timestamp 时间戳
        @param kline_type K线类型 kline 1分钟K线，kline_5min 5分钟K线，kline_15min 15分钟K线
        """
        if kline_type == const.MARKET_TYPE_KLINE:
            name = "EVENT_KLINE"
            exchange = "Kline"
        elif kline_type == const.MARKET_TYPE_KLINE_5M:
            name = "EVENT_KLINE_5MIN"
            exchange = "Kline.5min"
        elif kline_type == const.MARKET_TYPE_KLINE_15M:
            name = "EVENT_KLINE_15MIN"
            exchange = "Kline.15min"
        else:
            logger.error("kline_type error! kline_type:", kline_type, caller=self)
            return
        routing_key = "{platform}.{symbol}".format(platform=platform, symbol=symbol)
        queue = "{server_id}.{exchange}.{routing_key}".format(server_id=config.server_id,
                                                              exchange=exchange,
                                                              routing_key=routing_key)
        data = {
            "platform": platform,
            "symbol": symbol,
            "open": open,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
            "timestamp": timestamp,
            "kline_type": kline_type
        }
        super(EventKline, self).__init__(name, exchange, queue, routing_key, data=data)

    def parse(self):
        """ 解析self._data数据
        """
        kline = Kline(**self.data)
        return kline


class EventOrderbook(Event):
    """ 订单薄事件
    * NOTE:
        订阅：业务模块
        发布：行情服务
    """

    def __init__(self, platform=None, symbol=None, asks=None, bids=None, timestamp=None):
        """ 初始化
        """
        name = "EVENT_ORDERBOOK"
        exchange = "Orderbook"
        routing_key = "{platform}.{symbol}".format(platform=platform, symbol=symbol)
        queue = "{server_id}.{exchange}.{routing_key}".format(server_id=config.server_id,
                                                              exchange=exchange,
                                                              routing_key=routing_key)
        data = {
            "platform": platform,
            "symbol": symbol,
            "asks": asks,
            "bids": bids,
            "timestamp": timestamp
        }
        super(EventOrderbook, self).__init__(name, exchange, queue, routing_key, data=data)

    def parse(self):
        """ 解析self._data数据
        """
        orderbook = Orderbook(**self.data)
        return orderbook


class EventTrade(Event):
    """ 交易事件
    * NOTE:
        订阅：业务模块
        发布：行情服务
    """

    def __init__(self, platform=None, symbol=None, action=None, price=None, quantity=None, timestamp=None):
        """ 初始化
        """
        name = "EVENT_TRADE"
        exchange = "Trade"
        routing_key = "{platform}.{symbol}".format(platform=platform, symbol=symbol)
        queue = "{server_id}.{exchange}.{routing_key}".format(server_id=config.server_id,
                                                              exchange=exchange,
                                                              routing_key=routing_key)
        data = {
            "platform": platform,
            "symbol": symbol,
            "action": action,
            "price": price,
            "quantity": quantity,
            "timestamp": timestamp
        }
        super(EventTrade, self).__init__(name, exchange, queue, routing_key, data=data)

    def parse(self):
        """ 解析self._data数据
        """
        trade = Trade(**self.data)
        return trade


class EventCenter:
    """ 事件处理中心
    """

    def __init__(self):
        self._host = config.rabbitmq.get("host", "localhost")
        self._port = config.rabbitmq.get("port", 5672)
        self._username = config.rabbitmq.get("username", "guest")
        self._password = config.rabbitmq.get("password", "guest")
        self._protocol = None
        self._channel = None  # 连接通道
        self._connected = False  # 是否连接成功
        self._subscribers = []  # 订阅者 [(event, callback, multi), ...]
        self._event_handler = {}  # 事件对应的处理函数 {"exchange:routing_key": [callback_function, ...]}

        LoopRunTask.register(self._check_connection, 10)  # 检查连接是否正常

    def initialize(self):
        """ 初始化
        """
        asyncio.get_event_loop().run_until_complete(self.connect())

    @async_method_locker("EventCenter.subscribe")
    async def subscribe(self, event: Event, callback=None, multi=False):
        """ 注册事件
        @param event 事件
        @param callback 回调函数
        @param multi 是否批量订阅消息，即routing_key为批量匹配
        """
        logger.info("NAME:", event.name, "EXCHANGE:", event.exchange, "QUEUE:", event.queue, "ROUTING_KEY:",
                    event.routing_key, caller=self)
        self._subscribers.append((event, callback, multi))

    async def publish(self, event):
        """ 发布消息
        @param event 发布的事件对象
        """
        if not self._connected:
            logger.warn("RabbitMQ not ready right now!", caller=self)
            return
        data = event.dumps()
        await self._channel.basic_publish(payload=data, exchange_name=event.exchange, routing_key=event.routing_key)

    async def connect(self, reconnect=False):
        """ 建立TCP连接
        @param reconnect 是否是断线重连
        """
        logger.info("host:", self._host, "port:", self._port, caller=self)
        if self._connected:
            return

        # 建立连接
        try:
            transport, protocol = await aioamqp.connect(host=self._host, port=self._port, login=self._username,
                                                        password=self._password)
        except Exception as e:
            logger.error("connection error:", e, caller=self)
            return
        finally:
            # 如果已经有连接已经建立好，那么直接返回（此情况在连续发送了多个连接请求后，若干个连接建立好了连接）
            if self._connected:
                return
        channel = await protocol.channel()
        self._protocol = protocol
        self._channel = channel
        self._connected = True
        logger.info("Rabbitmq initialize success!", caller=self)

        # 创建默认的交换机
        exchanges = ["Orderbook", "Trade", "Kline", "EVENT_CONFIG", "EVENT_HEARTBEAT", "EVENT_ASSET", "EVENT_ORDER", ]
        for name in exchanges:
            await self._channel.exchange_declare(exchange_name=name, type_name="topic")
        logger.debug("create default exchanges success!", caller=self)

        # 如果是断线重连，那么直接绑定队列并开始消费数据，如果是首次连接，那么等待5秒再绑定消费（等待程序各个模块初始化完成）
        if reconnect:
            self._bind_and_consume()
        else:
            asyncio.get_event_loop().call_later(5, self._bind_and_consume)

    def _bind_and_consume(self):
        """ 绑定并开始消费事件消息
        """
        async def do_them():
            for event, callback, multi in self._subscribers:
                await self._initialize(event, callback, multi)
        SingleTask.run(do_them)

    async def _initialize(self, event: Event, callback=None, multi=False):
        """ 创建/绑定交易所相关消息队列
        @param event 订阅的事件
        @param callback 回调函数
        @param multi 是否批量订阅消息，即routing_key为批量匹配
        """
        if event.queue:
            await self._channel.queue_declare(queue_name=event.queue, auto_delete=True)
            queue_name = event.queue
        else:
            result = await self._channel.queue_declare(exclusive=True)
            queue_name = result["queue"]
        await self._channel.queue_bind(queue_name=queue_name, exchange_name=event.exchange,
                                       routing_key=event.routing_key)
        await self._channel.basic_qos(prefetch_count=event.prefetch_count)  # 消息窗口大小，越大，消息推送越快，但也需要处理越快
        if callback:
            if multi:
                # 消费队列，routing_key为批量匹配，无需ack
                await self._channel.basic_consume(callback=callback, queue_name=queue_name, no_ack=True)
                logger.info("multi message queue:", queue_name, "callback:", callback, caller=self)
            else:
                # 消费队列，routing_key唯一确定，需要ack确定
                await self._channel.basic_consume(self._on_consume_event_msg, queue_name=queue_name)
                logger.info("queue:", queue_name, caller=self)
                self._add_event_handler(event, callback)

    async def _on_consume_event_msg(self, channel, body, envelope, properties):
        """ 收到订阅的事件消息
        @param channel 消息队列通道
        @param body 接收到的消息
        @param envelope 路由规则
        @param properties 消息属性
        """
        # logger.debug("exchange:", envelope.exchange_name, "routing_key:", envelope.routing_key,
        #              "body:", body, caller=self)
        try:
            key = "{exchange}:{routing_key}".format(exchange=envelope.exchange_name, routing_key=envelope.routing_key)
            # 执行事件回调函数
            funcs = self._event_handler[key]
            for func in funcs:
                SingleTask.run(func, envelope.exchange_name, envelope.routing_key, body)
        except:
            logger.error("event handle error! body:", body, caller=self)
            return
        finally:
            await self._channel.basic_client_ack(delivery_tag=envelope.delivery_tag)  # response ack

    def _add_event_handler(self, event: Event, callback):
        """ 增加事件处理回调函数
        * NOTE: {"exchange:routing_key": [callback_function, ...]}
        """
        key = "{exchange}:{routing_key}".format(exchange=event.exchange, routing_key=event.routing_key)
        if key in self._event_handler:
            self._event_handler[key].append(callback)
        else:
            self._event_handler[key] = [callback]
        logger.debug("event handlers:", self._event_handler.keys(), caller=self)

    async def _check_connection(self, *args, **kwargs):
        """ 检查连接是否正常，如果连接已经断开，那么立即发起连接
        """
        if self._connected and self._channel and self._channel.is_open:
            logger.debug("RabbitMQ connection ok.", caller=self)
            return
        logger.error("CONNECTION LOSE! START RECONNECT RIGHT NOW!", caller=self)
        self._connected = False
        self._protocol = None
        self._channel = None
        self._event_handler = {}
        SingleTask.run(self.connect, reconnect=True)
