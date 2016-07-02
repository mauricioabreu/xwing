import asyncio
import sys
sys.path.append('.')  # NOQA

from xwing.mailbox import Node


async def pong_actor(mailbox):
    sender, message = await mailbox.recv()
    await mailbox.send(sender, 'pong')


async def ping_actor(mailbox, pong_id):
    await mailbox.send(pong_id, 'ping')
    print('Got: ', await mailbox.recv())


if __name__ == '__main__':
    # python examples/actor/server.py
    hub_frontend, hub_backend = '127.0.0.1:5555', '/var/tmp/xwing.socket'
    loop = asyncio.get_event_loop()

    # Start a actor node by which we can spawn actors
    node = Node(loop, hub_frontend, hub_backend)
    pong_id = node.spawn(pong_actor)  # Spawn an pong actor and get its id
    node.spawn(ping_actor, pong_id)
    node.run_until_complete()