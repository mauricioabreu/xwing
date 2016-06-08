import sys
sys.path.append('.')

import asyncio
import time
import subprocess
import logging
logging.basicConfig(level=logging.DEBUG)

from xwing.socket.client import Client


FRONTEND_ADDRESS = '127.0.0.1:5555'


def setup_module(module):
    module.hub_process = subprocess.Popen('bin/xwing')
    time.sleep(1)
    module.server_process = subprocess.Popen(['python', 'tests/run_server.py'])


def teardown_module(module):
    module.hub_process.kill()
    module.server_process.kill()


class TestIntegration:

    @classmethod
    def setup_class(cls):
        cls.loop = asyncio.get_event_loop()
        cls.client = Client(cls.loop, FRONTEND_ADDRESS)

        async def connect(cls):
            while True:
                try:
                    cls.connection = await cls.client.connect('server0')
                except ConnectionError:
                    await asyncio.sleep(1)
                    continue
                else:
                    break

        cls.loop.run_until_complete(asyncio.wait_for(connect(cls), 30))

    @classmethod
    def teardown_class(cls):
        cls.connection.close()

    def test_send_and_recv_str(self):
        async def run(self):
            data = 'ping'
            await self.connection.send_str(data)
            await self.connection.recv_str()
            return True

        event_loop = asyncio.get_event_loop()
        assert event_loop.run_until_complete(run(self))

    def test_send_and_recv(self):
        async def run(self):
            data = b'ping'
            await self.connection.send(data)
            await self.connection.recv()
            return True

        event_loop = asyncio.get_event_loop()
        assert event_loop.run_until_complete(run(self))
