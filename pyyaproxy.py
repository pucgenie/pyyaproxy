#!/usr/bin/python3
import asyncio, socket
import os, sys
"""
License: StackOverflow default CC BY-SA 4.0, author: gawel https://stackoverflow.com/a/21297354/2714781
"""
class TargetClient(asyncio.Protocol):
	# premature optimization? https://stackoverflow.com/a/53388520/2714781
	__slots__ = ('transport', 'proxied_client',)

	def connection_made(self, transport,):
		"""
		As soon as this connection to the TargetServer is established, optimize for low latency and remember transport.
		"""
		self.transport = transport
		transport.get_extra_info('socket').setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1,)

	def data_received(self, data,):
		"""
		Forward data to the correct client.
		Fortunately, the client surely is connected (as long as nothing is broken - in which case we wouldn't even try to correct that and we will just let the connection die).
		"""
		# blocking call
		self.proxied_client.write(data)

		# measure TCP_NODELAY (Nagle's algorithm NOT to be used) impact somehow
		print('server2client_n_bytes: ', len(data), file=sys.stdout,)

	def connection_lost(self, *args,):
		"""
		Reduced error message logging by preventing follow-up errors.
		"""
		self.proxied_client.close()
		# I don't want to risk it
		#self.proxied_client = None


class PassTCPServer(asyncio.Protocol):
	target_server = None # (host, port,)

	# premature optimization? https://stackoverflow.com/a/53388520/2714781
	__slots__ = ('transport', 'target_client', 'connectedFuture',)

	def connection_made(self, transport,):
		"""
		As soon as a client connects, connect through to target_server.
		"""
		# removed as we introduced __slots__. At the moment debugging isn't necessary. Keep it here for the idea.
		# assert self.connectedFuture == 'bug#1'
		
		# save the transport
		self.transport = transport
		transport.get_extra_info('socket').setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1,)
		assert self.target_client is None, """It's not that simple^^"""
		def onConnectedTarget(connectedFuture, self=self,):
			try:
				protocol, target_client = connectedFuture.result()
			except socket.gaierror as gaierr:
				# logging
				print('failed: Client', transport.get_extra_info('peername'), ', target_server_error: ', gaierr, file=sys.stderr,)
				self.transport.close()

			# logging
			print('connected: Client', transport.get_extra_info('peername'), file=sys.stderr,)
			
			target_client.proxied_client = self.transport
			self.target_client = target_client
			# gray hair if you need to debug
			self.connectedFuture = None
		# Why does it know what loop is?
		self.connectedFuture = asyncio.Task(loop.create_connection(TargetClient, *PassTCPServer.target_server,), loop=loop,)
		self.connectedFuture.add_done_callback(onConnectedTarget)

	def data_received(self, data,):
		"""
		When a client connects, it will most likely be faster to begin to send data before we were able to connect to TargetServer.
		TODO: Would raise/except be faster than this simple if construct?
		"""
		# gray hair if you need to debug
		raceIt = self.connectedFuture
		if raceIt is None:
			# blocking call
			self.target_client.transport.write(data)
			# measure TCP_NODELAY (Nagle's algorithm NOT to be used) impact somehow
			# (ignored on first segment (raceIt))
			print('client2server_n_bytes: ', len(data), file=sys.stdout,)
		else:
			# In case of TCP Fast Open or slow Target connection establishment
			def afterConnectedTarget(connectedFuture):
				try:
					connectedFuture.result()[1].transport.write(data)
				except socket.gaierror as gaierr:
					# logging
					# maybe `self` is not visible?
					print('failed: Client', self.transport.get_extra_info('peername'), ', target_server_error: ', gaierr, ', duplicate_log_message: expected', file=sys.stderr,)
					self.transport.close()
			raceIt.add_done_callback(afterConnectedTarget)
	
	def connection_lost(self, *args,):
		"""
		Logs the client which just disconnected.
		Reduced error message logging by preventing follow-up errors.
		"""
		# logging
		print(f"disconnected: Client{self.transport.get_extra_info('peername')}", file=sys.stderr,)
		# If connecting fails early, we don't have access to any target_client here.
		if self.target_client is not None:
			self.target_client.transport.close()
			# I don't want to risk it
			#self.target_client = None


if __name__ == '__main__':
	def intOrDefault(x, y,):
		return y if x is None else int(x)

	# I don't like base10 IPv4 addresses and TCP port numbers so I won't support a.b.c.d:e notation parsing.
	# If it crashes there you know what to do, right? ... amirite?
	PassTCPServer.target_server = (os.getenv('TARGET_SERVER_FQDN'), intOrDefault(os.getenv('TARGET_SERVER_PORT'), 25565,),)
	relay_bind = (os.getenv('RELAY_BIND_IP', '0.0.0.0',), intOrDefault(os.getenv('RELAY_BIND_PORT'), PassTCPServer.target_server[1],),)

	# premature optimization?
	del intOrDefault

	loop = asyncio.get_event_loop()
	# blocking call
	asyncio.run(loop.create_server(PassTCPServer, *relay_bind,))

	# premature optimization?
	del relay_bind
	
	loop.run_forever()
