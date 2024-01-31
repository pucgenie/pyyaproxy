#!/usr/bin/python3
from asyncio import Protocol, Task, new_event_loop
from socket import IPPROTO_TCP, TCP_NODELAY, AI_PASSIVE, gaierror
from sys import stdout, stderr
"""
License: StackOverflow default CC BY-SA 4.0, author: gawel https://stackoverflow.com/a/21297354/2714781
"""
class Stats4DownAndUp():
	statsCollectors = [[], [],]

	def __str__(self):
		return f"""self is {"None" if self is None else "something"}"""

class TargetClient(Protocol):
	# premature optimization? https://stackoverflow.com/a/53388520/2714781
	__slots__ = ('transport', 'proxied_client',)

	def __init__(self):
		self.transport = None
		self.proxied_client = None

	def connection_made(self, transport,):
		"""
		As soon as this connection to the TargetServer is established, optimize for low latency and remember transport.
		"""
		self.transport = transport
		transport.get_extra_info('socket').setsockopt(IPPROTO_TCP, TCP_NODELAY, 1,)

	def data_received(self, data,):
		"""
		Forward data to the correct client.
		Fortunately, the client surely is connected (as long as nothing is broken - in which case we wouldn't even try to correct that and we will just let the connection die).
		"""
		try:
			# non-blocking call, buffers outgoing data for loop
			self.proxied_client.write(data)
			# measure TCP_NODELAY (Nagle's algorithm NOT to be used) impact somehow
			print('server2client_n_bytes: ', len(data), file=stdout,)
		except gaierror as gaierr:
			print(f"disconnected: Target{self.transport.get_extra_info('peername')}", file=stderr,)
			# connection lost.

	def connection_lost(self, *args,):
		"""
		Reduced error message logging by preventing follow-up errors.
		"""
		self.proxied_client.close()
		# I don't want to risk it
		#self.proxied_client = None


class PassTCPServer(Protocol):
	# premature optimization? https://stackoverflow.com/a/53388520/2714781
	__slots__ = ('transport', 'target_client', 'target_connecting',)
	
	target_server = None # (host, port,)

	def __init__(self):
		self.transport = None
		self.target_client = None
		self.target_connecting = 'bug#1'

	def connection_made(self, transport,):
		"""
		As soon as a client connects, connect through to target_server.
		"""
		assert self.target_connecting == 'bug#1'
		
		# save the transport
		self.transport = transport
		transport.get_extra_info('socket').setsockopt(IPPROTO_TCP, TCP_NODELAY, 1,)
		assert self.target_client is None, """It's not that simple^^"""
		def onConnectedTarget(self, target_connecting,):
			try:
				protocol, target_client = target_connecting.result()
				# logging
				print('connected: Client', transport.get_extra_info('peername'), file=stderr,)

				# debug code
				print(self == protocol, self == target_client)
				
				target_client.proxied_client = self.transport
				self.target_client = target_client
				# gray hair if you need to debug
				self.target_connecting = None
			except gaierror as gaierr:
				# logging
				print('failed: Client', transport.get_extra_info('peername'), ', target_server_error: ', gaierr, file=stderr,)
				self.transport.close()

		# loop is in global scope
		self.target_connecting = loop.create_task(loop.create_connection(TargetClient, *PassTCPServer.target_server,))
		self.target_connecting.add_done_callback(lambda target_connecting, self=self: onConnectedTarget(self, target_connecting,))

	def data_received(self, data,):
		"""
		When a client connects, it will most likely be faster to begin to send data before we were able to connect to TargetServer.
		TODO: Would raise/except be faster than this simple if construct?
		"""
		# gray hair if you need to debug
		raceIt = self.target_connecting
		if raceIt is not None:
			# In case of TCP Fast Open or slow Target connection establishment
			def afterConnectedTarget(target_connecting, data,):
				try:
					target_connecting.result()[1].transport.write(data)
				except gaierror as gaierr:
					# logging
					# maybe `self` is not visible?
					print('failed: Client', self.transport.get_extra_info('peername'), ', target_server_error: ', gaierr, ', duplicate_log_message: expected', file=stderr,)
					self.transport.close()
			raceIt.add_done_callback(lambda target_connecting, data=data: afterConnectedTarget(target_connecting, data,))
		else:
			# blocking call
			self.target_client.transport.write(data)
			# measure TCP_NODELAY (Nagle's algorithm NOT to be used) impact somehow
			# (ignored on first segment (raceIt))
			print('client2server_n_bytes: ', len(data), file=stdout,)
	
	def connection_lost(self, *args,):
		"""
		Logs the client which just disconnected.
		Reduced error message logging by preventing follow-up errors.
		"""
		# logging
		print(f"disconnected: Client{self.transport.get_extra_info('peername')}", file=stderr,)
		# If connecting fails early, we don't have access to any target_client here.
		if self.target_client is not None:
			self.target_client.transport.close()
			# I don't want to risk it
			#self.target_client = None


if __name__ == '__main__':
	def intOrDefault(x, y,):
		return y if x is None else int(x)

	from os import getenv, environ
	from signal import signal, SIGUSR1
	# I don't like base10 IPv4 addresses and TCP port numbers so I won't support a.b.c.d:e notation parsing.
	# If it crashes there you know what to do, right? ... amirite?
	PassTCPServer.target_server = (environ['TARGET_SERVER_FQDN'], intOrDefault(getenv('TARGET_SERVER_PORT'), 25565,),)

	# global context
	loop = new_event_loop()
	serverTask = loop.create_task(loop.create_server(PassTCPServer, getenv('RELAY_BIND_IP', '0.0.0.0',), intOrDefault(getenv('RELAY_BIND_PORT'), PassTCPServer.target_server[1],), flags=AI_PASSIVE | TCP_NODELAY, backlog=2,))
	# premature optimization?
	del intOrDefault
	
	def printStats():
		print(str(Stats4DownAndUp), file=stderr,)
	signal(SIGUSR1, printStats,)

	try:
		loop.run_forever()
	finally:
		serverTask.done()
