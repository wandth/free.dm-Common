'''
This module defines an IPC server communicating via UXD sockets
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
    from typing import Union, Type, Optional, TypeVar
    
    # free.dm Imports
    from freedm.utils.ipc.server.base import IPCSocketServer, freedmIPCSocketCreation
    from freedm.utils.ipc.connection import Connection, ConnectionType
except ImportError as e:
    from freedm.utils.exceptions import freedmModuleImport
    raise freedmModuleImport(e)


US = TypeVar('US', bound='UXDSocketServer')


class UXDSocketServer(IPCSocketServer):
    '''
    An IPC Server using Unix Domain sockets implemented as async contextmanager.
    This server keeps track 
    '''
    
    def __init__(
            self,
            path: Union[str, Path]=None,
            loop: Optional[Type[asyncio.AbstractEventLoop]]=None,
            limit: Optional[int]=None,
            chunksize: Optional[int]=None,
            max_connections: Optional[int]=None,
            mode: Optional[Union[ConnectionType]]=None
            ) -> None:
        
        super(self.__class__, self).__init__(loop, limit, chunksize, max_connections, mode)
        self.path = path

    async def __aenter__(self) -> US:
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
            server = await asyncio.start_unix_server(self._onConnectionEstablished, loop=self.loop, sock=sock, limit=self.limit)
        else:
            server = await asyncio.start_unix_server(self._onConnectionEstablished, loop=self.loop, sock=sock)
        self._context = server
            
        # Return connection class
        return self

    async def __aexit__(self, *args) -> None:
        # Call parent method to make sure all pendinf connections are being cancelled
        await super(self.__class__, self).__aexit__(*args)
        # Stop the server and remove UXD socket
        try:
            self._context.close()
        except Exception as e:
            print('IPC: Can\'t close UXD socket server', self._context, e)
        try:   
            await self._context.wait_closed()
        except Exception as e:
            print('IPC Can\'t wait until UXD server closes', self._context, e)    
        try:
            os.remove(self.path)
        except Exception as e:
            raise freedmIPCSocketCreation(f'Could not remove socket file "{self.path}" after closing the server ({e})')
        print('IPC: Closed UXD Socket Server')
        
    def _assembleConnection(self, reader: Type[asyncio.StreamReader], writer: Type[asyncio.StreamWriter]) -> Optional[Connection]:
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
                'mode': self.mode or ConnectionType.PERSISTENT,
                'creation': time.time(),
                'update': time.time() 
                }
            )