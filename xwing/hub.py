import os
import logging
import socket
import array
import asyncio

SERVICE_POSITIVE_ANSWER = b'+'
SERVICE_PING = b'!'
BUFFER_SIZE = 4096

log = logging.getLogger(__name__)


class Hub:
    '''The Socket Hub implementation.

    Provides a Hub that known how to connect sockets
    between clients and servers.

    :param frontend_endpoint: Endpoint where clients will connect.
    :type frontend_endpoint: str
    :param backend_endpoint: Endpoint where servers will connect.
    :type frontend_endpoint: str
    :param polling_interval: Interval used on polling socket in seconds.

    Usage::

      >>> from xwing.hub import Hub
      >>> hub = Hub('0.0.0.0:5555', '/var/run/xwing.socket')
      >>> hub.run()
    '''

    def __init__(self, frontend_endpoint, backend_endpoint):
        self.frontend_endpoint = frontend_endpoint
        self.backend_endpoint = backend_endpoint
        self.loop = asyncio.get_event_loop()
        self.stop_event = asyncio.Event()
        self.services = {}

    def run(self):
        '''Run the server loop'''
        tasks = [
            asyncio.ensure_future(self.run_frontend(self.frontend_endpoint)),
            asyncio.ensure_future(self.run_backend(self.backend_endpoint))
        ]

        try:
            done, pending = self.loop.run_until_complete(asyncio.wait(
                tasks, return_when=asyncio.FIRST_EXCEPTION))

            # If a exception happned on any of waited tasks
            # this forces the exception to buble up
            for future in done:
                future.result()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        '''Loop stop.'''
        self.stop_event.set()
        for task in asyncio.Task.all_tasks():
            task.cancel()

        self.loop.run_forever()
        self.loop.close()

    async def run_frontend(self, tcp_address, backlog=10, timeout=0.1):
        log.info('Running frontend loop')
        address, port = tcp_address.split(':')
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.bind((address, int(port)))
            sock.listen(backlog)
            sock.settimeout(timeout)

            while not self.stop_event.is_set():
                try:
                    conn, address = await self.loop.sock_accept(sock)
                except socket.timeout:
                    await asyncio.sleep(timeout)
                    continue

                service = await self.loop.sock_recv(conn, BUFFER_SIZE)
                if not service:
                    break

                if service not in self.services:
                    self.loop.sock_sendall(conn, b'-Service not found\r\n')
                    continue

                # detach and pack FD into a array
                fd = conn.detach()
                fds = array.array("I", [fd])

                try:
                    # Send FD to server connection
                    server_conn = self.services[service]
                    server_conn.sendmsg([b'1'], [(socket.SOL_SOCKET,
                                                  socket.SCM_RIGHTS, fds)])
                except BrokenPipeError:  # NOQA
                    # If connections is broken, the server is gone
                    # so we need to remove it from services
                    del self.services[service]
                    conn = socket.fromfd(fd, socket.AF_INET,
                                         socket.SOCK_STREAM)
                    conn.sendall(b'-Service not found\r\n')
                    conn.close()

    async def run_backend(self, unix_address, backlog=10, timeout=0.1):
        log.info('Running backend loop')
        try:
            # Make sure that there is no zombie socket
            os.unlink(unix_address)
        except OSError:
            pass

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.bind(unix_address)
            sock.listen(backlog)
            sock.settimeout(timeout)

            while not self.stop_event.is_set():
                try:
                    conn, address = await self.loop.sock_accept(sock)
                except socket.timeout:
                    await asyncio.sleep(timeout)
                    continue

                service = await self.loop.sock_recv(conn, BUFFER_SIZE)
                if not service:  # connection was closed
                    break

                server_conn = self.services.get(service)
                if server_conn:
                    try:
                        server_conn.sendall(SERVICE_PING)
                    except BrokenPipeError:  # NOQA
                        # If connections is broken, the server is gone
                        # so we need to remove it from services
                        del self.services[service]
                    else:
                        conn.sendall(b'-Service already exists\r\n')
                        continue

                # TODO we should detach the fd from connection
                # can it be that conn variable will be collected
                # and the connection will be closed?
                self.services[service] = conn
                await self.loop.sock_sendall(conn, SERVICE_POSITIVE_ANSWER)
