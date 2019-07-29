# -*- coding:utf-8 -*-

"""
Config module.

Author: HuangTao
Date:   2018/05/03
Email:  huangtao@ifclover.com
"""

import json

from quant.utils import tools
from quant.utils import logger


class Config:
    """ Config module will load a json file like `config.json` and parse the content to json object.
        1. Configure content must be key-value pair, and `key` will be set as Config module's attributes;
        2. Invoking Config module's attributes cat get those values;
        3. Some `key` name is upper case are the build-in, and all `key` will be set to lower case:
            SERVER_ID: Server id, every running process has a unique id.
            RUN_TIME_UPDATE: If this server support run-time-update(receive EventConfig), True or False, default is False.
            LOG: Logger print config.
            RABBITMQ: RabbitMQ config, default is None.
            MONGODB: MongoDB config, default is None.
            REDIS: Redis config, default is None.
            PLATFORMS: Trading Exchanges config, default is {}.
            HEARTBEAT: Server heartbeat config, default is {}.
            HTTP_SERVER: HTTP server config, default is None.
            PROXY: HTTP proxy config, default is None.
    """

    def __init__(self):
        self.server_id = None
        self.run_time_update = False
        self.log = {}
        self.rabbitmq = {}
        self.mongodb = {}
        self.redis = {}
        self.platforms = {}
        self.heartbeat = {}
        self.http_server = None
        self.proxy = None

    def initialize(self):
        if self.run_time_update:
            from quant.event import EventConfig
            EventConfig(self.server_id).subscribe(self._on_event_config)

    def loads(self, config_file=None):
        """ Load config file.

        Args:
            config_file: config json file.
        """
        configures = {}
        if config_file:
            try:
                with open(config_file) as f:
                    data = f.read()
                    configures = json.loads(data)
            except Exception as e:
                print(e)
                exit(0)
            if not configures:
                print("config json file error!")
                exit(0)
        self._update(configures)

    async def _on_event_config(self, data):
        """ Config event update.

        Args:
            data: New config received from ConfigEvent.
        """
        server_id = data["server_id"]
        params = data["params"]
        if server_id != self.server_id:
            logger.error("Server id error:", server_id, caller=self)
            return
        if not isinstance(params, dict):
            logger.error("params format error:", params, caller=self)
            return

        params["SERVER_ID"] = self.server_id
        params["RUN_TIME_UPDATE"] = self.run_time_update
        self._update(params)
        logger.info("config update success!", caller=self)

    def _update(self, update_fields):
        """ Update config attributes.

        Args:
            update_fields: Update fields.
        """
        self.server_id = update_fields.get("SERVER_ID", tools.get_uuid1())
        self.run_time_update = update_fields.get("RUN_TIME_UPDATE", False)
        self.log = update_fields.get("LOG", {})
        self.rabbitmq = update_fields.get("RABBITMQ", None)
        self.mongodb = update_fields.get("MONGODB", None)
        self.redis = update_fields.get("REDIS", None)
        self.platforms = update_fields.get("PLATFORMS", {})
        self.heartbeat = update_fields.get("HEARTBEAT", {})
        self.http_server = update_fields.get("HTTP_SERVER", None)
        self.proxy = update_fields.get("PROXY", None)

        if self.http_server:
            port = self.http_server.get("port")
            apis = self.http_server.get("apis")
            middlewares = self.http_server.get("middlewares", [])
            ext_uri = self.http_server.get("ext_uri", [])
            if not isinstance(port, int) or port < 1024 or port > 65535:
                logger.error("http port error! port:", port, caller=self)
                exit(0)
            if not isinstance(apis, list):
                logger.error("http api pathes error! apis:", apis, caller=self)
                exit(0)
            if not isinstance(middlewares, list):
                logger.error("http middlewares error! middlewares:", middlewares, caller=self)
                exit(0)
            if not isinstance(ext_uri, list):
                logger.error("http ext_uri error! ext_uri:", ext_uri, caller=self)
                exit(0)

        for k, v in update_fields.items():
            setattr(self, k, v)


config = Config()
