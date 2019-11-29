# -*- coding:utf-8 -*-

"""
Binance Future Trade module.
https://binanceapitest.github.io/Binance-Futures-API-doc

Author: HuangTao
Date:   2019/09/18
Email:  huangtao@ifclover.com
"""

import json
import copy
import hmac
import hashlib
from urllib.parse import urljoin

from quant.error import Error
from quant.utils import tools
from quant.utils import logger
from quant.const import BINANCE_FUTURE
from quant.order import Order
from quant.position import Position
from quant.utils.web import Websocket
from quant.asset import Asset, AssetSubscribe
from quant.tasks import SingleTask, LoopRunTask
from quant.utils.http_client import AsyncHttpRequests
from quant.utils.decorator import async_method_locker
from quant.order import ORDER_ACTION_BUY, ORDER_ACTION_SELL, ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET
from quant.order import ORDER_STATUS_SUBMITTED, ORDER_STATUS_PARTIAL_FILLED, ORDER_STATUS_FILLED, \
    ORDER_STATUS_CANCELED, ORDER_STATUS_FAILED
from quant.order import TRADE_TYPE_BUY_OPEN, TRADE_TYPE_SELL_OPEN, TRADE_TYPE_SELL_CLOSE, TRADE_TYPE_BUY_CLOSE


__all__ = ("BinanceFutureRestAPI", "BinanceFutureTrade", )


class BinanceFutureRestAPI:
    """ Binance Future REST API client.

    Attributes:
        host: HTTP request host.
        access_key: Account's ACCESS KEY.
        secret_key: Account's SECRET KEY.
    """

    def __init__(self, host, access_key, secret_key):
        """initialize REST API client."""
        self._host = host
        self._access_key = access_key
        self._secret_key = secret_key

    async def ping(self):
        """Test connectivity to the Rest API."""
        uri = "/fapi/v1/ping"
        success, error = await self.request("GET", uri)
        return success, error

    async def server_time(self):
        """Test connectivity to the Rest API and get the current server time."""
        uri = "/fapi/v1/time"
        success, error = await self.request("GET", uri)
        return success, error

    async def exchange_information(self):
        """Current exchange trading rules and symbol information"""
        uri = "/fapi/v1/exchangeInfo"
        success, error = await self.request("GET", uri)
        return success, error

    async def get_orderbook(self, symbol, limit=100):
        """Get orderbook information.

        Args:
            symbol: Trade pair name.
            limit: The length of orderbook, Default 100, max 1000. Valid limits:[5, 10, 20, 50, 100, 500, 1000]

        Returns:
            success: Success results, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        uri = "/fapi/v1/depth"
        params = {
            "symbol": symbol,
            "limit": limit
        }
        success, error = await self.request("GET", uri, params)
        return success, error

    async def get_trade(self, symbol, limit=500):
        """Get recent trades (up to last 500).

        Args:
            symbol: Trade pair name.
            limit: The length of trade, Default 500, max 1000.

        Returns:
            success: Success results, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        uri = "/fapi/v1/trades"
        params = {
            "symbol": symbol,
            "limit": limit
        }
        success, error = await self.request("GET", uri, params)
        return success, error

    async def get_kline(self, symbol, interval="1m", start=None, end=None, limit=20):
        """Kline/candlestick bars for a symbol. Klines are uniquely identified by their open time.

        Args:
            symbol: Trade pair name.
            interval: Kline interval, defaut `1m`, valid: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M.
            start: Start time(millisecond).
            end: End time(millisecond).
            limit: The length of kline, Default 20, max 1000.

        Returns:
            success: Success results, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        uri = "/fapi/v1/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        if start:
            params["startTime"] = start
        if end:
            params["endTime"] = end
        success, error = await self.request("GET", uri, params)
        return success, error

    async def get_user_account(self):
        """ Get current account information.

        Returns:
            success: Success results, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        uri = "/fapi/v1/account"
        ts = tools.get_cur_timestamp_ms()
        params = {
            "timestamp": str(ts)
        }
        success, error = await self.request("GET", uri, params, auth=True)
        return success, error

    async def get_position(self):
        """ Get current position information.

        Returns:
            success: Success results, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        uri = "/fapi/v1/positionRisk"
        ts = tools.get_cur_timestamp_ms()
        params = {
            "timestamp": str(ts)
        }
        success, error = await self.request("GET", uri, params, auth=True)
        return success, error

    async def create_order(self, action, symbol, price, quantity, client_order_id=None):
        """ Create an order.
        Args:
            action: Trade direction, BUY or SELL.
            symbol: Symbol name, e.g. BTCUSDT.
            price: Price of each contract.
            quantity: The buying or selling quantity.
            client_order_id: A unique id for the order. Automatically generated if not sent.

        Returns:
            success: Success results, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        uri = "/fapi/v1/order"
        data = {
            "symbol": symbol,
            "side": action,
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": quantity,
            "price": price,
            "recvWindow": "5000",
            "timestamp": tools.get_cur_timestamp_ms()
        }
        if client_order_id:
            data["newClientOrderId"] = client_order_id
        success, error = await self.request("POST", uri, body=data, auth=True)
        return success, error

    async def revoke_order(self, symbol, order_id, client_order_id):
        """ Cancelling an unfilled order.
        Args:
            symbol: Symbol name, e.g. BTCUSDT.
            order_id: Order id.
            client_order_id: Client order id.

        Returns:
            success: Success results, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        uri = "/fapi/v1/order"
        params = {
            "symbol": symbol,
            "orderId": order_id,
            "origClientOrderId": client_order_id,
            "timestamp": tools.get_cur_timestamp_ms()
        }
        success, error = await self.request("DELETE", uri, params=params, auth=True)
        return success, error

    async def get_order_status(self, symbol, order_id, client_order_id):
        """ Check an order's status.

        Args:
            symbol: Symbol name, e.g. BTCUSDT.
            order_id: Order id.
            client_order_id: Client order id.

        Returns:
            success: Success results, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        uri = "/fapi/v1/order"
        params = {
            "symbol": symbol,
            "orderId": str(order_id),
            "origClientOrderId": client_order_id,
            "timestamp": tools.get_cur_timestamp_ms()
        }
        success, error = await self.request("GET", uri, params=params, auth=True)
        return success, error

    async def get_all_orders(self, symbol, order_id=None, start=None, end=None, limit=500):
        """ Get all account orders; active, canceled, or filled.
        Args:
            symbol: Symbol name, e.g. BTCUSDT.
            order_id: Order id, default None.
            start: Start time(millisecond)
            end: End time(millisecond).
            limit: Limit return length, default 500, max 1000.

        Returns:
            success: Success results, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        uri = "/fapi/v1/allOrders"
        params = {
            "symbol": symbol,
            "limit": limit,
            "timestamp": tools.get_cur_timestamp_ms()
        }
        if order_id:
            params["orderId"] = order_id
        if start:
            params["startTime"] = start
        if end:
            params["endTime"] = end
        success, error = await self.request("GET", uri, params=params, auth=True)
        return success, error

    async def get_open_orders(self, symbol):
        """ Get all open order information.
        Args:
            symbol: Symbol name, e.g. BTCUSDT.

        Returns:
            success: Success results, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        uri = "/fapi/v1/openOrders"
        params = {
            "symbol": symbol,
            "timestamp": tools.get_cur_timestamp_ms()
        }
        success, error = await self.request("GET", uri, params=params, auth=True)
        return success, error

    async def get_listen_key(self):
        """ Get listen key, start a new user data stream

        Returns:
            success: Success results, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        uri = "/fapi/v1/listenKey"
        params = {
            "timestamp": tools.get_cur_timestamp_ms()
        }
        success, error = await self.request("POST", uri, params=params, auth=True)
        return success, error

    async def put_listen_key(self, listen_key):
        """ Keepalive a user data stream to prevent a time out.

        Args:
            listen_key: Listen key.

        Returns:
            success: Success results, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        uri = "/fapi/v1/listenKey"
        params = {
            "listenKey": listen_key,
            "timestamp": tools.get_cur_timestamp_ms()
        }
        success, error = await self.request("PUT", uri, params=params, auth=True)
        return success, error

    async def delete_listen_key(self, listen_key):
        """ Delete a listen key.

        Args:
            listen_key: Listen key.

        Returns:
            success: Success results, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        uri = "/fapi/v1/listenKey"
        params = {
            "listenKey": listen_key,
            "timestamp": tools.get_cur_timestamp_ms()
        }
        success, error = await self.request("DELETE", uri, params=params, auth=True)
        return success, error

    async def request(self, method, uri, params=None, body=None, headers=None, auth=False):
        """ Do HTTP request.

        Args:
            method: HTTP request method. GET, POST, DELETE, PUT.
            uri: HTTP request uri.
            params: HTTP query params.
            body:   HTTP request body.
            headers: HTTP request headers.
            auth: If this request requires authentication.

        Returns:
            success: Success results, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        url = urljoin(self._host, uri)
        data = {}
        if params:
            data.update(params)
        if body:
            data.update(body)
        if not headers:
            headers = {}
        if data:
            query = "&".join(["=".join([str(k), str(v)]) for k, v in data.items()])
        else:
            query = ""
        if auth and query:
            signature = hmac.new(self._secret_key.encode(), query.encode(), hashlib.sha256).hexdigest()
            query += "&signature={s}".format(s=signature)
            headers["X-MBX-APIKEY"] = self._access_key
        if query:
            url += ("?" + query)
        _, success, error = await AsyncHttpRequests.fetch(method, url, headers=headers, timeout=10)
        return success, error


class BinanceFutureTrade:
    """ Binance Future Trade module. You can initialize trade object with some attributes in kwargs.

    Attributes:
        account: Account name for this trade exchange.
        strategy: What's name would you want to created for you strategy.
        symbol: Symbol name for your trade.
        host: HTTP request host. (default "https://fapi.binance.com")
        wss: Websocket address. (default "wss://fstream.binance.com")
        access_key: Account's ACCESS KEY.
        secret_key Account's SECRET KEY.
        asset_update_callback: You can use this param to specific a async callback function when you initializing Trade
            object. `asset_update_callback` is like `async def on_asset_update_callback(asset: Asset): pass` and this
            callback function will be executed asynchronous when received AssetEvent.
        order_update_callback: You can use this param to specific a async callback function when you initializing Trade
            object. `order_update_callback` is like `async def on_order_update_callback(order: Order): pass` and this
            callback function will be executed asynchronous when some order state updated.
        init_success_callback: You can use this param to specific a async callback function when you initializing Trade
            object. `init_success_callback` is like `async def on_init_success_callback(success: bool, error: Error, **kwargs): pass`
            and this callback function will be executed asynchronous after Trade module object initialized successfully.
    """

    def __init__(self, **kwargs):
        """Initialize Trade module."""
        e = None
        if not kwargs.get("account"):
            e = Error("param account miss")
        if not kwargs.get("strategy"):
            e = Error("param strategy miss")
        if not kwargs.get("symbol"):
            e = Error("param symbol miss")
        if not kwargs.get("host"):
            kwargs["host"] = "https://fapi.binance.com"
        if not kwargs.get("wss"):
            kwargs["wss"] = "wss://fstream.binance.com"
        if not kwargs.get("access_key"):
            e = Error("param access_key miss")
        if not kwargs.get("secret_key"):
            e = Error("param secret_key miss")
        if e:
            logger.error(e, caller=self)
            if kwargs.get("init_success_callback"):
                SingleTask.run(kwargs["init_success_callback"], False, e)
            return

        self._account = kwargs["account"]
        self._strategy = kwargs["strategy"]
        self._platform = BINANCE_FUTURE
        self._symbol = kwargs["symbol"]
        self._host = kwargs["host"]
        self._wss = kwargs["wss"]
        self._access_key = kwargs["access_key"]
        self._secret_key = kwargs["secret_key"]
        self._asset_update_callback = kwargs.get("asset_update_callback")
        self._order_update_callback = kwargs.get("order_update_callback")
        self._position_update_callback = kwargs.get("position_update_callback")
        self._init_success_callback = kwargs.get("init_success_callback")

        self._ok = False  # Initialize successfully ?

        self._raw_symbol = self._symbol  # Row symbol name, same as Binance Exchange.

        self._listen_key = None  # Listen key for Websocket authentication.
        self._assets = {}  # Asset data. e.g. {"BTC": {"free": "1.1", "locked": "2.2", "total": "3.3"}, ... }
        self._orders = {}  # Order data. e.g. {order_no: order, ... }
        self._position = Position(self._platform, self._account, self._strategy, self._symbol)  # 仓位

        # Initialize our REST API client.
        self._rest_api = BinanceFutureRestAPI(self._host, self._access_key, self._secret_key)

        # Subscribe our AssetEvent.
        if self._asset_update_callback:
            AssetSubscribe(self._platform, self._account, self.on_event_asset_update)

        # Create a loop run task to reset listen key every 20 minutes.
        LoopRunTask.register(self._reset_listen_key, 60 * 20)

        # Create a loop run task to check position information per 1 second.
        LoopRunTask.register(self._check_position_update, 1)

        # Create a loop run task to send ping message to server per 30 seconds.
        # LoopRunTask.register(self._send_heartbeat_msg, 10)

        # Create a coroutine to initialize Websocket connection.
        SingleTask.run(self._init_websocket)

    @property
    def assets(self):
        return copy.copy(self._assets)

    @property
    def orders(self):
        return copy.copy(self._orders)

    @property
    def rest_api(self):
        return self._rest_api

    async def _init_websocket(self):
        """ Initialize Websocket connection.
        """
        # Get listen key first.
        success, error = await self._rest_api.get_listen_key()
        if error:
            e = Error("get listen key failed: {}".format(error))
            logger.error(e, caller=self)
            SingleTask.run(self._init_success_callback, False, e)
            return
        self._listen_key = success["listenKey"]
        uri = "/ws/" + self._listen_key
        url = urljoin(self._wss, uri)
        self._ws = Websocket(url, self.connected_callback, process_callback=self.process)
        self._ws.initialize()

    async def _reset_listen_key(self, *args, **kwargs):
        """ Reset listen key.
        """
        if not self._listen_key:
            logger.error("listen key not initialized!", caller=self)
            return
        await self._rest_api.put_listen_key(self._listen_key)
        logger.info("reset listen key success!", caller=self)

    # async def _send_heartbeat_msg(self, *args, **kwargs):
    #     """Send ping to server."""
    #     hb = {"ping": tools.get_cur_timestamp_ms()}
    #     await self._ws.send(hb)

    async def connected_callback(self):
        """ After websocket connection created successfully, pull back all open order information.
        """
        logger.info("Websocket connection authorized successfully.", caller=self)
        order_infos, error = await self._rest_api.get_open_orders(self._raw_symbol)
        if error:
            e = Error("get open orders error: {}".format(error))
            SingleTask.run(self._init_success_callback, False, e)
            return
        for order_info in order_infos:
            order_no = "{}_{}".format(order_info["orderId"], order_info["clientOrderId"])
            if order_info["status"] == "NEW":
                status = ORDER_STATUS_SUBMITTED
            elif order_info["status"] == "PARTIAL_FILLED":
                status = ORDER_STATUS_PARTIAL_FILLED
            elif order_info["status"] == "FILLED":
                status = ORDER_STATUS_FILLED
            elif order_info["status"] == "CANCELED":
                status = ORDER_STATUS_CANCELED
            elif order_info["status"] == "REJECTED":
                status = ORDER_STATUS_FAILED
            elif order_info["status"] == "EXPIRED":
                status = ORDER_STATUS_FAILED
            else:
                logger.warn("unknown status:", order_info, caller=self)
                continue

            info = {
                "platform": self._platform,
                "account": self._account,
                "strategy": self._strategy,
                "order_no": order_no,
                "action": order_info["side"],
                "order_type": order_info["type"],
                "symbol": self._symbol,
                "price": order_info["price"],
                "quantity": order_info["origQty"],
                "remain": float(order_info["origQty"]) - float(order_info["executedQty"]),
                "status": status,
                "trade_type": int(order_info["clientOrderId"][-1]),
                "ctime": order_info["updateTime"],
                "utime": order_info["updateTime"]
            }
            order = Order(**info)
            self._orders[order_no] = order
            SingleTask.run(self._order_update_callback, copy.copy(order))

        self._ok = True
        SingleTask.run(self._init_success_callback, True, None)

    async def create_order(self, action, price, quantity, order_type=ORDER_TYPE_LIMIT):
        """ Create an order.

        Args:
            action: Trade direction, BUY or SELL.
            price: Price of each contract.
            quantity: The buying or selling quantity.
            order_type: Limit order or market order, LIMIT or MARKET.

        Returns:
            order_no: Order ID if created successfully, otherwise it's None.
            error: Error information, otherwise it's None.
        """
        if float(quantity) > 0:
            if action == ORDER_ACTION_BUY:
                trade_type = TRADE_TYPE_BUY_OPEN
            else:
                trade_type = TRADE_TYPE_SELL_CLOSE
        else:
            if action == ORDER_ACTION_BUY:
                trade_type = TRADE_TYPE_BUY_CLOSE
            else:
                trade_type = TRADE_TYPE_SELL_OPEN
        quantity = abs(float(quantity))
        price = tools.float_to_str(price)
        quantity = tools.float_to_str(quantity)
        client_order_id = tools.get_uuid1().replace("-", "")[:21] + str(trade_type)
        result, error = await self._rest_api.create_order(action, self._raw_symbol, price, quantity, client_order_id)
        if error:
            return None, error
        order_no = "{}_{}".format(result["orderId"], result["clientOrderId"])
        return order_no, None

    async def revoke_order(self, *order_nos):
        """ Revoke (an) order(s).

        Args:
            order_nos: Order id list, you can set this param to 0 or multiple items. If you set 0 param, you can cancel
                all orders for this symbol(initialized in Trade object). If you set 1 param, you can cancel an order.
                If you set multiple param, you can cancel multiple orders. Do not set param length more than 100.

        Returns:
            Success or error, see bellow.
        """
        # If len(order_nos) == 0, you will cancel all orders for this symbol(initialized in Trade object).
        if len(order_nos) == 0:
            order_infos, error = await self._rest_api.get_open_orders(self._raw_symbol)
            if error:
                return False, error
            for order_info in order_infos:
                _, error = await self._rest_api.revoke_order(self._raw_symbol, order_info["orderId"],
                                                             order_info["clientOrderId"])
                if error:
                    return False, error
            return True, None

        # If len(order_nos) == 1, you will cancel an order.
        if len(order_nos) == 1:
            order_id, client_order_id = order_nos[0].split("_")
            success, error = await self._rest_api.revoke_order(self._raw_symbol, order_id, client_order_id)
            if error:
                return order_nos[0], error
            else:
                return order_nos[0], None

        # If len(order_nos) > 1, you will cancel multiple orders.
        if len(order_nos) > 1:
            success, error = [], []
            for order_no in order_nos:
                order_id, client_order_id = order_no.split("_")
                _, e = await self._rest_api.revoke_order(self._raw_symbol, order_id, client_order_id)
                if e:
                    error.append((order_no, e))
                else:
                    success.append(order_no)
            return success, error

    async def get_open_order_nos(self):
        """ Get open order no list.
        """
        success, error = await self._rest_api.get_open_orders(self._raw_symbol)
        if error:
            return None, error
        order_nos = []
        for order_info in success:
            order_no = "{}_{}".format(order_info["orderId"], order_info["clientOrderId"])
            order_nos.append(order_no)
        return order_nos, None

    @async_method_locker("BinanceTrade.process.locker")
    async def process(self, msg):
        """ Process message that received from Websocket connection.

        Args:
            msg: message received from Websocket connection.
        """
        logger.debug("msg:", json.dumps(msg), caller=self)
        e = msg.get("e")
        if e == "ORDER_TRADE_UPDATE":  # Order update.
            self._update_order(msg["o"])

    async def _check_position_update(self, *args, **kwargs):
        """Check position update."""
        if not self._ok:
            return
        update = False
        success, error = await self._rest_api.get_position()
        if error:
            return

        position_info = None
        for item in success:
            if item["symbol"] == self._raw_symbol:
                position_info = item
                break

        if not self._position.utime:  # Callback position info when initialized.
            update = True
            self._position.update()
        size = float(position_info["positionAmt"])
        average_price = float(position_info["entryPrice"])
        if size > 0:
            if self._position.long_quantity != size:
                update = True
                self._position.update(0, 0, size, average_price, 0)
        elif size < 0:
            if self._position.short_quantity != abs(size):
                update = True
                self._position.update(abs(size), average_price, 0, 0, 0)
        elif size == 0:
            if self._position.long_quantity != 0 or self._position.short_quantity != 0:
                update = True
                self._position.update()
        if update:
            await self._position_update_callback(copy.copy(self._position))

    def _update_order(self, order_info):
        """ Order update.

        Args:
            order_info: Order information.

        Returns:
            Return order object if or None.
        """
        if order_info["s"] != self._raw_symbol:
            return
        order_no = "{}_{}".format(order_info["i"], order_info["c"])

        if order_info["X"] == "NEW":
            status = ORDER_STATUS_SUBMITTED
        elif order_info["X"] == "PARTIAL_FILLED":
            status = ORDER_STATUS_PARTIAL_FILLED
        elif order_info["X"] == "FILLED":
            status = ORDER_STATUS_FILLED
        elif order_info["X"] == "CANCELED":
            status = ORDER_STATUS_CANCELED
        elif order_info["X"] == "REJECTED":
            status = ORDER_STATUS_FAILED
        elif order_info["X"] == "EXPIRED":
            status = ORDER_STATUS_FAILED
        else:
            return
        order = self._orders.get(order_no)
        if not order:
            info = {
                "platform": self._platform,
                "account": self._account,
                "strategy": self._strategy,
                "order_no": order_no,
                "action": order_info["S"],
                "order_type": order_info["o"],
                "symbol": self._symbol,
                "price": order_info["p"],
                "quantity": order_info["q"],
                "ctime": order_info["T"]
            }
            order = Order(**info)
            self._orders[order_no] = order
        order.remain = float(order_info["q"]) - float(order_info["z"])
        order.avg_price = order_info["L"]
        order.status = status
        order.utime = order_info["T"]
        order.trade_type = int(order_no[-1])
        SingleTask.run(self._order_update_callback, copy.copy(order))

    async def on_event_asset_update(self, asset: Asset):
        """ Asset data update callback.

        Args:
            asset: Asset object.
        """
        self._assets = asset
        SingleTask.run(self._asset_update_callback, asset)
