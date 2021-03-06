from lib.interpreters.constants import Position
import lib.utility as utility
import random


class Command(object):
	def __init__(self, game, key, comm=False):
		self.game = game
		self.key = key
		self.commandBuffer = {}
		self.comm = comm
		self.exceptionOccurred = False

	class CommandException(Exception):
		pass

	def prepare(self):
		self.commandBuffer = {}

	def execute(self, args, sender):
		print ('BUG: This command has no overriding execute function.')

	def output(self):
		for mobile, bufferList in self.commandBuffer.iteritems():
			bufferString = '\n\r'.join( bufferList )

			mobile.sendToClient( bufferString, comm=(self.comm if not self.exceptionOccurred else False) )

	def appendToCommandBuffer(self, key, string):
		if key in self.commandBuffer:
			self.commandBuffer[key].append(string)
		else:
			self.commandBuffer[key] = [string,]

	def checkPosition(self, sender, allowedPositions, override=None):
		if isinstance(allowedPositions, list) and sender.position in allowedPositions:
			return
		elif sender.position == allowedPositions:
			return
		else:
			if sender.position == Position.sleeping:
				msg = 'In your dreams, or what?'
			elif sender.position == Position.resting:
				msg = 'You are too relaxed.'
			elif sender.position == Position.fighting:
				msg = 'You can\'t do that in combat.'
			elif sender.position == Position.standing:
				msg = 'You aren\'t fighting anyone.'

		if override:
			msg = override

		raise self.CommandException(msg)

	def checkIfCanCommunicate(self, sender):
		if sender.getStat('nochan'):
			raise self.CommandException('You have been muted.')

	def getCombatTargetByArgs(self, sender, args):
		try:
			return sender.getCombatTargetByArgs(args)
		except sender.MobileException as e:
			raise self.CommandException(str(e))

	def getMobileFromListByName(self, needle, haystack):
		if not haystack:
			raise self.CommandException('You don\'t see them here.')
		for candidate in haystack:
			if utility.matchList(needle, candidate.keywords):
				return candidate
		raise self.CommandException('You don\'t see them here.')


	def getItemFromListByName(self, needle, haystack):
		if not haystack:
			raise self.CommandException('You don\'t see that here.')
		for candidate in haystack:
			if utility.matchList(needle, candidate.keywords):
				return candidate
		raise self.CommandException('You don\'t see that here.')

	def getTargetFromListByName(self, needle, haystack):
		if not haystack:
			raise self.CommandException('You don\'t see them here.')
		for candidate in haystack:
			if utility.matchList(needle, candidate.keywords):
				return candidate
		print 'getTargetFromListByName is DEPRECATED, use getMobileFromListByName or getItemFromListByName instead.'
		raise self.CommandException('You don\'t see them here.')

	def areThereAnyExits(self, room):
		if len(room.exits) == 0:
			raise self.NoExitsException()

	def simpleSuccessCheck(self, percentage):
		if random.randint(0,100) >= percentage:
			raise self.CommandException('Skill \'{skill}\' failed.'.format(skill=self.key))

	def hasAtLeastOneArgument(self, args):
		if not args:
			raise self.CommandException('You need at least one argument to use this command.')

	def notAffectedBy(self, target, affects):
		if isinstance(affects, list):
			for affect in affects:
				if affect in [affect.name for affect in target.affects]:
					raise self.CommandException('Target is already affected by {affect}.'.format(affect=affect.name))
		else:
			if affects in [affect.name for affect in target.affects]:
				raise self.CommandException('Target is already affected by {affect}.'.format(affect=affect.name))

	def isLegalCombatTarget(self, target):
		if target.is_player and target.room.getStat('no_pkill'):
			raise self.CommandException('You can\'t fight players here.')
		if target.room.getStat('no_combat'):
			raise self.CommandException('You can\'t fight in this room.')
		elif target.isAffectedBy('just died'):
			raise self.CommandException('Give them a chance to breathe before fighting again.')

	def move(self, sender, direction):
		self.test(self.checkPosition, (sender, [Position.standing,]))

		oldRoom = sender.room

		newRoom = next((exit.destination for exit in sender.room.exits if exit.key == direction), None)
		if newRoom:
			oldRoom = sender.room
			sender.room = newRoom
		else:
			raise self.CommandException('You can\'t go that way.')

		msg = 'You leave {direction}.\n\rYou arrive at {newRoom}.'.format(direction=direction,newRoom=newRoom.getName(sender))
		self.appendToCommandBuffer(sender, msg)

		if not sender.isAffectedBy('sneak'):
			for mobile in sender.inRoomExcept(sender,room=oldRoom):
				msg = '{sender} leaves {direction}.'.format(sender=sender,direction=direction)
				self.appendToCommandBuffer(mobile, msg)

			for mobile in sender.inRoomExcept(sender):
				msg = '{sender} has arrived.'.format(sender=sender)
				self.appendToCommandBuffer(mobile, msg)

		sender.setLag(1)

	def notSelfTargetable(self, target, sender):
		if target == sender:
			raise self.CommandException('You can\'t target yourself.')

	def test(self, function, args, override=None):
		if not isinstance(args, tuple):
			args = (args,)
		try:
			returnValue = function( *args )
		except self.CommandException as e:
			if override:
				raise self.CommandException(override)
			else:
				raise

		return returnValue

	def error(self, message):
		raise self.CommandException(message)