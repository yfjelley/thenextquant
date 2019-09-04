# -*- coding:utf-8 -*-

"""
OKEx 币币杠杆 REST API 封装
https://www.okex.me/docs/zh/

Author: HuangTao
Date:   2019/02/19
"""

import time
import json
import hmac
import copy
import zlib
import base64
from urllib.parse import urljoin

from quant.error import Error
from quant.utils import tools
from quant.utils import logger
from quant.const import OKEX_MARGIN
from quant.order import Order
from quant.tasks import SingleTask
from quant.utils.websocket import Websocket
from quant.asset import Asset, AssetSubscribe
from quant.utils.decorator import async_method_locker
from quant.utils.http_client import AsyncHttpRequests
from quant.order import ORDER_ACTION_BUY, ORDER_ACTION_SELL
from quant.order import ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET
from quant.order import ORDER_STATUS_SUBMITTED, ORDER_STATUS_PARTIAL_FILLED, ORDER_STATUS_FILLED, \
    ORDER_STATUS_CANCELED, ORDER_STATUS_FAILED


__all__ = ("OKExMarginRestAPI", "OKExMarginTrade", )


class OKExMarginRestAPI:
    """ OKEx 币币杠杆 REST API 封装
    """

    def __init__(self, host, access_key, secret_key, passphrase):
        """ 初始化
        @param host 请求的host
        @param access_key 请求的access_key
        @param secret_key 请求的secret_key
        @param passphrase API KEY的密码
        """
        self._host = host
        self._access_key = access_key
        self._secret_key = secret_key
        self._passphrase = passphrase

    async def get_margin_accounts(self):
        """ 获取币币杠杆账户资产列表
        """
        uri = "/api/margin/v3/accounts"
        success, error = await self.request("GET", uri, auth=True)
        return success, error

    async def get_margin_account(self, instrument_id):
        """ 单一币对账户信息
        """
        uri = "/api/margin/v3/accounts/{instrument_id}".format(instrument_id=instrument_id)
        success, error = await self.request("GET", uri, auth=True)
        return success, error

    async def get_availability(self):
        """ 获取币币杠杆账户的借币配置信息，包括当前最大可借、借币利率、最大杠杆倍数。
        """
        success, error = await self.request("GET", "/api/margin/v3/accounts/availability", auth=True)
        return success, error

    async def borrow(self, instrument_id, currency, amount):
        """ 在某个币币杠杆账户里进行借币。
        @param instrument_id 杠杆币对名称
        @param currency 币种
        @param amount 借币数量
        """
        body = {
            "instrument_id": instrument_id,
            "currency": currency,
            "amount": amount
        }
        success, error = await self.request("POST", "/api/margin/v3/accounts/borrow", body=body, auth=True)
        return success, error

    async def repayment(self, instrument_id, currency, amount, borrow_id=None):
        """ 在某个币币杠杆账户里进行还币。
        @param instrument_id 杠杆币对名称
        @param currency 币种
        @param amount 还币数量
        @param borrow_id 借币记录ID，不填时还整个币对的币
        """
        body = {
            "instrument_id": instrument_id,
            "currency": currency,
            "amount": amount
        }
        if borrow_id:
            body["borrow_id"] = borrow_id
        success, error = await self.request("POST", "/api/margin/v3/accounts/borrow", body=body, auth=True)
        return success, error

    async def create_order(self, action, instrument_id, price, quantity, order_type=ORDER_TYPE_LIMIT):
        """ 下单
        @param action 操作类型 BUY SELL
        @param instrument_id 币对名称
        @param price 价格(市价单传入None)
        @param quantity 买入或卖出的数量 限价买入或卖出数量 / 市价买入金额 / 市价卖出数量
        @param order_type 交易类型，市价 / 限价
        """
        info = {
            "side": "buy" if action == ORDER_ACTION_BUY else "sell",
            "instrument_id": instrument_id,
            "margin_trading": 2
        }
        if order_type == ORDER_TYPE_LIMIT:
            info["type"] = "limit"
            info["price"] = price
            info["size"] = quantity
        elif order_type == ORDER_TYPE_MARKET:
            info["type"] = "market"
            if action == ORDER_ACTION_BUY:
                info["notional"] = quantity  # 买入金额，市价买入是必填notional
            else:
                info["size"] = quantity  # 卖出数量，市价卖出时必填size
        else:
            logger.error("order_type error! order_type:", order_type, caller=self)
            return None
        success, error = await self.request("POST", "/api/margin/v3/orders", body=info, auth=True)
        return success, error

    async def revoke_order(self, instrument_id, order_id):
        """ 撤单
        @param instrument_id 币对名称
        @param order_id 订单ID
        """
        body = {
            "instrument_id": instrument_id,
            "order_id": order_id
        }
        uri = "/api/margin/v3/cancel_orders/{order_id}".format(order_id=order_id)
        success, error = await self.request("POST", uri, body=body, auth=True)
        return success, error

    async def revoke_orders(self, instrument_id, order_ids):
        """ 批量撤单
        @param instrument_id 币对名称
        @param order_ids 订单id列表
        """
        assert isinstance(order_ids, list)
        body = {
            "instrument_id": instrument_id,
            "order_ids": order_ids
        }
        success, error = await self.request("POST", "/api/margin/v3/cancel_batch_orders", body=body, auth=True)
        return success, error

    async def get_order_status(self, instrument_id, order_id):
        """ 获取订单信息
        @param instrument_id 币对名称
        @param order_id 订单ID
        """
        params = {
            "instrument_id": instrument_id
        }
        uri = "/api/margin/v3/orders/{order_id}".format(order_id=order_id)
        success, error = await self.request("GET", uri, params=params, auth=True)
        return success, error

    async def get_open_orders(self, instrument_id):
        """ 获取当前还未完全成交的订单信息
        @param instrument_id 交易对
        * NOTE: 查询上限最多100个订单
        """
        params = {
            "instrument_id": instrument_id
        }
        result, error = await self.request("GET", "/api/margin/v3/orders_pending", params=params, auth=True)
        return result, error

    async def get_order_list(self, instrument_id, status, _from=1, to=100, limit=100):
        """ 获取订单列表
        @param instrument_id 币对名称
        @param status 订单状态 all 所有状态 / open 未成交 / part_filled 部分成交 / canceling 撤销中 / filled 已成交 /
                                        cancelled 已撤销 / failure 下单失败 / ordering 下单中
        @param _from 起始编号，默认为1
        @param to 结束编号，默认为100
        @param limit 最多返回数据条数，默认为100
        """
        uri = "/api/futures/v3/orders/{instrument_id}".format(instrument_id=instrument_id)
        params = {
            "status": status,
            "from": _from,
            "to": to,
            "limit": limit
        }
        success, error = await self.request("GET", uri, params=params, auth=True)
        return success, error

    async def request(self, method, uri, params=None, body=None, headers=None, auth=False):
        """ 发起请求
        @param method 请求方法 GET / POST / DELETE / PUT
        @param uri 请求uri
        @param params dict 请求query参数
        @param body dict 请求body数据
        @param headers 请求http头
        @param auth boolean 是否需要加入权限校验
        """
        if params:
            query = "&".join(["{}={}".format(k, params[k]) for k in sorted(params.keys())])
            uri += "?" + query
        url = urljoin(self._host, uri)

        # 增加签名
        if auth:
            timestamp = str(time.time()).split(".")[0] + "." + str(time.time()).split(".")[1][:3]
            if body:
                body = json.dumps(body)
            else:
                body = ""
            message = str(timestamp) + str.upper(method) + uri + str(body)
            mac = hmac.new(bytes(self._secret_key, encoding="utf8"), bytes(message, encoding="utf-8"),
                           digestmod="sha256")
            d = mac.digest()
            sign = base64.b64encode(d)

            if not headers:
                headers = {}
            headers["Content-Type"] = "application/json"
            headers["OK-ACCESS-KEY"] = self._access_key.encode().decode()
            headers["OK-ACCESS-SIGN"] = sign.decode()
            headers["OK-ACCESS-TIMESTAMP"] = str(timestamp)
            headers["OK-ACCESS-PASSPHRASE"] = self._passphrase
        _, success, error = await AsyncHttpRequests.fetch(method, url, body=body, headers=headers, timeout=10)
        return success, error


class OKExMarginTrade(Websocket):
    """ OKEx Margin Trade模块
    """

    def __init__(self, **kwargs):
        """ 初始化
        """
        e = None
        if not kwargs.get("account"):
            e = Error("param account miss")
        if not kwargs.get("strategy"):
            e = Error("param strategy miss")
        if not kwargs.get("symbol"):
            e = Error("param symbol miss")
        if not kwargs.get("host"):
            kwargs["host"] = "https://www.okex.com"
        if not kwargs.get("wss"):
            kwargs["wss"] = "wss://real.okex.com:10442"
        if not kwargs.get("access_key"):
            e = Error("param access_key miss")
        if not kwargs.get("secret_key"):
            e = Error("param secret_key miss")
        if not kwargs.get("passphrase"):
            e = Error("param passphrase miss")
        if e:
            logger.error(e, caller=self)
            if kwargs.get("init_success_callback"):
                SingleTask.run(kwargs["init_success_callback"], False, e)
            return

        self._account = kwargs["account"]
        self._strategy = kwargs["strategy"]
        self._platform = OKEX_MARGIN
        self._symbol = kwargs["symbol"]
        self._host = kwargs["host"]
        self._wss = kwargs["wss"]
        self._access_key = kwargs["access_key"]
        self._secret_key = kwargs["secret_key"]
        self._passphrase = kwargs["passphrase"]
        self._asset_update_callback = kwargs.get("asset_update_callback")
        self._order_update_callback = kwargs.get("order_update_callback")
        self._init_success_callback = kwargs.get("init_success_callback")

        self._raw_symbol = self._symbol.replace("/", "-")  # 转换成交易所对应的交易对格式
        self._order_channel = "spot/order:{symbol}".format(symbol=self._raw_symbol)  # 订单订阅频道

        url = self._wss + "/ws/v3"
        super(OKExMarginTrade, self).__init__(url, send_hb_interval=5)
        self.heartbeat_msg = "ping"

        self._assets = {}  # 资产 {"BTC": {"free": "1.1", "locked": "2.2", "total": "3.3"}, ... }
        self._orders = {}  # 订单 {"order_no": order, ... }

        # 初始化 REST API 对象
        self._rest_api = OKExMarginRestAPI(self._host, self._access_key, self._secret_key, self._passphrase)

        # 初始化资产订阅
        if self._asset_update_callback:
            AssetSubscribe(self._platform, self._account, self.on_event_asset_update)

        self.initialize()

    @property
    def assets(self):
        return copy.copy(self._assets)

    @property
    def orders(self):
        return copy.copy(self._orders)

    @property
    def rest_api(self):
        return self._rest_api

    async def connected_callback(self):
        """ 建立连接之后，授权登陆，然后订阅order和position
        """
        # 身份验证
        timestamp = str(time.time()).split(".")[0] + "." + str(time.time()).split(".")[1][:3]
        message = str(timestamp) + "GET" + "/users/self/verify"
        mac = hmac.new(bytes(self._secret_key, encoding="utf8"), bytes(message, encoding="utf8"), digestmod="sha256")
        d = mac.digest()
        signature = base64.b64encode(d).decode()
        data = {
            "op": "login",
            "args": [self._access_key, self._passphrase, timestamp, signature]
        }
        await self.ws.send_json(data)

    @async_method_locker("OKExMarginTrade.process_binary.locker")
    async def process_binary(self, raw):
        """ 处理websocket上接收到的消息
        @param raw 原始的压缩数据
        """
        decompress = zlib.decompressobj(-zlib.MAX_WBITS)
        msg = decompress.decompress(raw)
        msg += decompress.flush()
        msg = msg.decode()
        if msg == "pong":  # 心跳返回
            return
        msg = json.loads(msg)
        logger.debug("msg:", msg, caller=self)

        # 登陆成功之后再订阅数据
        if msg.get("event") == "login":
            if not msg.get("success"):
                e = Error("Websocket connection authorized failed: {}".format(msg))
                logger.error(e, caller=self)
                if self._init_success_callback:
                    SingleTask.run(self._init_success_callback, False, e)
                return
            logger.info("Websocket connection authorized successfully.", caller=self)

            # 获取当前等待成交和部分成交的订单信息
            order_infos, error = await self._rest_api.get_open_orders(self._raw_symbol)
            if error:
                e = Error("get open orders error: {}".format(msg))
                if self._init_success_callback:
                    SingleTask.run(self._init_success_callback, False, e)
                return
            for order_info in order_infos:
                order_info["ctime"] = order_info["created_at"]
                order_info["utime"] = order_info["timestamp"]
                order = self._update_order(order_info)
                if self._order_update_callback:
                    SingleTask.run(self._order_update_callback, copy.copy(order))

            # 订阅 order
            data = {
                "op": "subscribe",
                "args": [self._order_channel]
            }
            await self.ws.send_json(data)
            return

        # 订阅返回消息
        if msg.get("event") == "subscribe":
            if msg.get("channel") == self._order_channel:
                if self._init_success_callback:
                    SingleTask.run(self._init_success_callback, True, None)
            else:
                if self._init_success_callback:
                    e = Error("subscribe order event error: {}".format(msg))
                    SingleTask.run(self._init_success_callback, False, e)
            return

        # 订单更新
        if msg.get("table") == "spot/order":
            for data in msg["data"]:
                data["ctime"] = data["timestamp"]
                data["utime"] = data["last_fill_time"]
                order = self._update_order(data)
                if order and self._order_update_callback:
                    SingleTask.run(self._order_update_callback, copy.copy(order))

    async def create_order(self, action, price, quantity, order_type=ORDER_TYPE_LIMIT):
        """ 创建订单
        @param action 交易方向 BUY/SELL
        @param price 委托价格
        @param quantity 委托数量
        @param order_type 委托类型 LIMIT / MARKET
        """
        price = tools.float_to_str(price)
        quantity = tools.float_to_str(quantity)
        result, error = await self._rest_api.create_order(action, self._raw_symbol, price, quantity, order_type)
        if error:
            return None, error
        if not result["result"]:
            return None, result
        return result["order_id"], None

    async def revoke_order(self, *order_nos):
        """ 撤销订单
        @param order_nos 订单号列表，可传入任意多个，如果不传入，那么就撤销所有订单
        * NOTE: 单次调用最多只能撤销4个订单，如果订单超过4个，请多次调用
        """
        # 如果传入order_nos为空，即撤销全部委托单
        if len(order_nos) == 0:
            order_infos, error = await self._rest_api.get_open_orders(self._raw_symbol)
            if error:
                return False, error
            for order_info in order_infos:
                order_no = order_info["order_id"]
                _, error = await self._rest_api.revoke_order(self._raw_symbol, order_no)
                if error:
                    return False, error
            return True, None

        # 如果传入order_nos为一个委托单号，那么只撤销一个委托单
        if len(order_nos) == 1:
            success, error = await self._rest_api.revoke_order(self._raw_symbol, order_nos[0])
            if error:
                return order_nos[0], error
            else:
                return order_nos[0], None

        # 如果传入order_nos数量大于1，那么就批量撤销传入的委托单
        if len(order_nos) > 1:
            success, error = [], []
            for order_no in order_nos:
                _, e = await self._rest_api.revoke_order(self._raw_symbol, order_no)
                if e:
                    error.append((order_no, e))
                else:
                    success.append(order_no)
            return success, error

    async def get_open_order_nos(self):
        """ 获取未完全成交订单号列表
        """
        success, error = await self._rest_api.get_open_orders(self._raw_symbol)
        if error:
            return None, error
        else:
            order_nos = []
            for order_info in success:
                order_nos.append(order_info["order_id"])
            return order_nos, None

    def _update_order(self, order_info):
        """ 更新订单信息
        @param order_info 订单信息
        """
        order_no = str(order_info["order_id"])
        state = order_info["state"]
        remain = float(order_info["size"]) - float(order_info["filled_size"])
        ctime = tools.utctime_str_to_mts(order_info["ctime"])
        utime = tools.utctime_str_to_mts(order_info["utime"])

        if state == "-2":
            status = ORDER_STATUS_FAILED
        elif state == "-1":
            status = ORDER_STATUS_CANCELED
        elif state == "0":
            status = ORDER_STATUS_SUBMITTED
        elif state == "1":
            status = ORDER_STATUS_PARTIAL_FILLED
        elif state == "2":
            status = ORDER_STATUS_FILLED
        else:
            logger.error("status error! order_info:", order_info, caller=self)
            return None

        order = self._orders.get(order_no)
        if order:
            order.remain = remain
            order.status = status
            order.price = order_info["price"]
        else:
            info = {
                "platform": self._platform,
                "account": self._account,
                "strategy": self._strategy,
                "order_no": order_no,
                "action": ORDER_ACTION_BUY if order_info["side"] == "buy" else ORDER_ACTION_SELL,
                "symbol": self._symbol,
                "price": order_info["price"],
                "quantity": order_info["size"],
                "remain": remain,
                "status": status,
                "avg_price": order_info["price"]
            }
            order = Order(**info)
            self._orders[order_no] = order
        order.ctime = ctime
        order.utime = utime
        if status in [ORDER_STATUS_FAILED, ORDER_STATUS_CANCELED, ORDER_STATUS_FILLED]:
            self._orders.pop(order_no)
        return order

    async def on_event_asset_update(self, asset: Asset):
        """ 资产数据更新回调
        """
        self._assets = asset
        SingleTask.run(self._asset_update_callback, asset)
