'''
This module defines IPC servers communicating via TCP or UXD sockets
@author: Thomas Wanderer
'''

try:
    # Imports
    import os
    import asyncio
    import socket
    import struct
    import time
    from pathlib import Path
    from typing import Union, Type, Optional, Set, TypeVar, List
    
    # free.dm Imports
    from freedm.utils.exceptions import freedmBaseException
    from freedm.utils.ipc.message import Message, CommandMessage
    from freedm.utils.ipc.connection import Connection, ConnectionType, ConnectionPool
except ImportError as e:
    from freedm.utils.exceptions import freedmModuleImport
    raise freedmModuleImport(e)


I = TypeVar('I', bound='IPCServer')
U = TypeVar('U', bound='UXDSocketServer')
T = TypeVar('T', bound='TCPSocketServer')


class IPCServer(object):
    '''
    A generic server implementation for IPC servers allowing to communicate with connected clients
    '''
    
    _connectionPool: ConnectionPool=ConnectionPool()
    
    def __init__(
            self,
            loop: Optional[Type[asyncio.AbstractEventLoop]]=None,
            limit: Optional[int]=None,
            chunksize: Optional[int]=None,
            max_connections: Optional[int]=None,
            mode: Optional[Union[ConnectionType]]=None
            ) -> None:
        self.loop = loop or asyncio.get_event_loop()
        self.limit = limit
        self.chunksize = chunksize
        self.mode = mode
        if isinstance(max_connections, int):
            self._connectionPool.max = max_connections
        
    async def __aenter__(self) -> I:
        '''A template function that should be implemented by any subclass'''
        return self
        
    async def __aexit__(self, *args) -> None:
        '''Cancel all pending connections in the connection pool'''
        for c in self._connectionPool:
            c.cancel()
        
    async def __await__(self) -> I:
        return await self.__aenter__()
    
    def _getConnection(self, reader: Type[asyncio.StreamReader], writer: Type[asyncio.StreamWriter]) -> Optional[Connection]:
        '''
        Builds a connection object based on the info we get from the reader/writer
        '''
        return Connection(
            socket=writer.get_extra_info('socket'),
            pid=None,
            uid=None,
            gis=None,
            client_address=None,
            server_address=None,
            reader=reader,
            writer=writer,
            state={
                'mode': self.mode or ConnectionType.TEXT_DATA,
                'creation': time.time(),
                'update': time.time()
                }
            )
    
    def _onConnectionRegister(self, reader: Type[asyncio.StreamReader], writer: Type[asyncio.StreamWriter]) -> asyncio.Task:
        '''
        Cares for the creation and recycling of connections for any new established session and subsequently hands over the further session handling
        '''
        # Check if we can accept?
        if self._connectionPool.isFull():
            return
        # Connection object
        connection = self._getConnection(reader, writer)
        # Create asyncio.Task for handling the session
        session = asyncio.ensure_future(self.handleConnection(connection))
        self._connectionPool.add(session)
        session.add_done_callback(lambda task: self._connectionPool.remove(session))
        return session
    
    async def handleConnection(self, connection: Connection) -> None:
        '''
        Handle the connection and listen for incoming messages
        '''
        # Authenticate
        auth = await self.authenticateConnection(connection)
        if auth:
            print('-> Connection was successfully authenticated')
        else:
            return
        
        # Simple IPC API
#         header = await reader.read(10)
#         if len(header) <= 3:
#             try:
#                 code = int(header)
#                 if CommandMessage.supports(code):
#                     await self._handleCommand(CommandMessage.get(code), connection)
#                     return
#             except:
#                 pass
        
        # Read data depending on the connection type and handle it
        if connection.state['mode'] == ConnectionType.TEXT_DATA:
            print('READING TEXT')
            while not connection.reader.at_eof():
                print(1)
                message = Message(
                    data=await connection.reader.read(self.limit or -1),
                    sender=connection
                    )
                print('=DATA', message.data)
#             try:
#                 lines = b''
#                 while not reader.at_eof():
#                     lines += await reader.readline()
#                 message = Message(
#                     data=lines,
#                     sender=connection
#                     )
#             except Exception as e:
#                 message = Message(
#                     data=await reader.read(self.limit or -1),
#                     sender=connection
#                     )
            connection.reader.feed_eof()
            await self.handleMessage(message)
        elif connection.state['mode'] == ConnectionType.STREAM_DATA:
            print('READING STREAM')
            while not connection.reader.at_eof():
                r = await connection.reader.read(self.chunksize or -1)
                message = Message(
                    data=r,
                    sender=connection
                    )
                await self.handleMessage(message)
        
        # Should we close conection    
        if connection.reader.at_eof():
            print('JA EOF = TRUE')
            await asyncio.sleep(.1)
            connection.writer.close()
            
    async def authenticateConnection(self, connection: Type[Connection]) -> bool:
        '''A template function that should be overwritten by any subclass if required'''
        return True
    
    async def _handleCommand(self, code: int, connection: Type[Connection]) -> None:
        '''A function implementing a minimal IPC API controlling the established connection between server & client'''
        if code == CommandMessage.PING:
            print('Ping')
            await self.sendMessage(CommandMessage.PONG.value, connection)
        elif code == CommandMessage.PONG:
            print('Pong')
        elif code == CommandMessage.SET_STREAM:
            # TODO: Change current connection to STREAM_DATA
            pass
        elif code == CommandMessage.SET_DATA:
            # TODO: Change current connection to TEXT_DATA
            pass
    
    async def handleMessage(self, message):
        '''A template function that should be overwritten by any subclass if required'''
        print(message.data.decode())
        
    async def sendMessage(self, message: Union[str, int, float], connection: Union[Type[Connection], List[Type[Connection]]]=None) -> None:
        '''
        Send a message to either one connection or a list of current connections
        '''
        if connection:
            connection.writer.write(str(message).encode())
            await connection.writer.drain()
#             if self.
#             
#             Hier überlegen on wir immer schliessen wollen oder icht
            connection.writer.write_eof()
#             await asyncio.sleep(.1)
#             connection.writer.close()
    
    async def close(self) -> None:
        '''Shutdown this server'''
        await self.__aexit__()
        
        

    # Handle or detect disconnects
    #https://stackoverflow.com/questions/27946786/how-to-detect-when-a-client-disconnects-from-a-uds-unix-domain-socket
    


class UXDSocketServer(IPCServer):
    '''
    An IPC Server using Unix Domain sockets implemented as async contextmanager.
    This server keeps track 
    '''
    
    # A register for active client connections
    _connections: Set[Type[Connection]] = set()
    
    # The context (This server)
    _context: None
    
    def __init__(self, path: Union[str, Path]=None, loop: Optional[Type[asyncio.AbstractEventLoop]]=None, limit: Optional[int]=None, chunksize: Optional[int]=None, mode: Optional[Union[ConnectionType]]=None) -> None:
        super(self.__class__, self).__init__(loop, limit, chunksize, mode)
        self.path = path

    async def __aenter__(self) -> U:
        # Create UXD socket (Based on https://www.pythonsheets.com/notes/python-socket.html)
        if not self.path:
            raise freedmIPCSocketCreation(f'Cannot create UXD socket (No socket file provided)')
        elif os.path.exists(self.path):
            if os.path.isdir(self.path):
                try:
                    os.rmdir()
                except:
                    raise freedmIPCSocketCreation(f'Cannot create UXD socket because "{self.path}" is a directory ({e})')
            else:
                try:
                    os.remove(self.path)
                except Exception as e:
                    raise freedmIPCSocketCreation(f'Cannot delete UXD socket file "{self.path}" ({e})')
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(self.path)
        except Exception as e:
            raise freedmIPCSocketCreation(f'Cannot create UXD socket file "{self.path}" ({e})')
        
        # Create UDP socket server
        if self.limit:
            server = await asyncio.start_unix_server(self._onConnectionRegister, loop=self.loop, sock=sock, limit=self.limit)
        else:
            server = await asyncio.start_unix_server(self._onConnectionRegister, loop=self.loop, sock=sock)
        self._context = server
        
        # Return connection class
        return self

    async def __aexit__(self, *args) -> None:
        await super(self.__class__, self).__aexit__(*args)
        print('IPC: We need to stop and cancel the UXD server')
        try:
            self._context.close()
        except Exception as e:
            print('Can\'t close UXD socket server', self._context, e)
        try:   
            await self._context.wait_closed()
        except Exception as e:
            print('Can\'t wait until server closes', self._context, e)    
        try:
            os.remove(self.path)
        except:
            raise freedmIPCSocketCreation(f'Could not remove socket file "{self.path}" after closing the server ({e})')
        print('IPC: Closed Socket Server')
        
    def _getConnection(self, reader: Type[asyncio.StreamReader], writer: Type[asyncio.StreamWriter]) -> Optional[Connection]:
        sock = writer.get_extra_info('socket')
        credentials = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
        pid, uid, gid = struct.unpack('3i', credentials)
        return Connection(
            socket=sock,
            pid=pid,
            uid=uid,
            gis=gid,
            client_address=None,
            server_address=None,
            reader=reader,
            writer=writer,
            state={
                'mode': self.mode or ConnectionType.TEXT_DATA,
                'creation': time.time(),
                'update': time.time() 
                }
            )

            
class TCPSocketServer(object):
    '''
    '''
    # https://www.pythonsheets.com/notes/python-socket.html
    # http://asyncio.readthedocs.io/en/latest/tcp_echo.html
    
#     addr = writer.get_extra_info('peername')
#     print("Received %r from %r" % (message, addr))

    # Mit IP6 oder nicht?
    # https://www.pythonsheets.com/notes/python-socket.html#simple-tcp-echo-server-through-ipv6
    # https://www.pythonsheets.com/notes/python-socket.html#disable-ipv6-only
    # 
            

class freedmIPCSocketCreation(freedmBaseException):
    '''
    Gets thrown when the IPC socket module cannot create a socket
    '''
    template = 'Cannot create IPC socket ({error})'
    
    
class freedmIPCMessageLimitOverrun(freedmBaseException):
    '''
    Gets thrown when the IPC socket receives a too large message which exceeds the set limit
    '''
    template = 'Message length exceeds set limit ({error})'