import combat
from mobile import Mobile
from room import Room
from exit import Exit
from area import Area
from item import Item
from mobile import Mobile
from interpreters.crafting import craftingInit
from lib.interpreters.constants import Range
import utility

from threading import Timer
from pymongo import MongoClient
from bson.objectid import ObjectId

class Game:
	def __init__(self):
		self.mobiles = []
		self.rooms = []
		self.areas = []
		self.recipes = []
		self.online = True

		self.clock = 0
		self.interval = 1.0

		self.client = MongoClient('localhost')  # FIX ME: this is set in two places, here and in tornadoServer.py. Should be only one.
		# self.client = MongoClient('mongodb://rdu:omghot4u@ds027769.mongolab.com:27769/redemptionunleashed')
		self.db = self.client.redemptionunleashed

		# Create some dummy content
		self.simpleInit()

		Timer(self.interval, self.updateGame).start()

	def getTargetMobile(self, caster, targetName, range, single=True):
		if range == Range.room:
			potentialTargets = [mobile for mobile in self.mobiles if mobile.room == caster.room]
		elif range == Range.area:
			potentialTargets = [mobile for mobile in self.mobiles if mobile.room.area == caster.room.area]
		elif range == Range.game:
			potentialTargets = self.mobiles

		if not potentialTargets:
			return False

		print potentialTargets

		targets = []

		for potentialTarget in potentialTargets:
			for keyword in potentialTarget.keywords:
				if keyword.startswith(targetName):
					targets.append(potentialTarget)
					continue

		if not targets:
			return False

		print targets

		targets.sort(key=lambda x: x.name)

		if single:
			# Prioritize targets in the room no matter what
			priorityTargets = [target for target in targets if target.room == caster.room]
			if priorityTargets:
				return priorityTargets[0]
			else:
				return targets[0]
		else:
			return targets

	def updateGame(self):
		self.clock += self.interval

		combatBuffer = {}
		for mobile in self.mobiles:
			mobile.update(self.interval)
			if self.clock % 3 * self.interval == 0:
				b2, target = combat.doCombat(mobile)

				if not target:
					continue

				mobile.sendToBuffer(b2['sender'].format(target=target.getName(mobile)))

				target.sendToBuffer(b2['target'].format(name=mobile.getName(target)))

				mobile.game.sendToBufferCondition(
					(lambda a: a.room == mobile.room and a is not mobile and a is not target),
					b2['room'], [mobile, target])

			if mobile.linkdead > 0 and not mobile.isAffectedBy('nervousness'):
				# Only decrement linkdead if a player is not nervous to prevent timing out in combat
				mobile.linkdead -= self.interval
				if mobile.linkdead <= 0:
					print ('{name} timed out from linkdead.'.format(name=mobile.name))
					mobile.leaveGame()

		for mobile in self.mobiles:
			if self.clock % 3 * self.interval == 0:
				if mobile.combatBuffer:
					mobile.appendEnemyConditionToBuffer()
					mobile.sendToClient(mobile.combatBuffer)
					mobile.clearBuffer()

		Timer(self.interval, self.updateGame).start()

	def endCombat(self, target):
		for mobile in self.mobiles:
			if mobile.combat is target:
				mobile.combat = None

	# The MESSAGE is always sent without a name, to be formatted in IF appropriate
	def sendCondition(self, condition, message, lookers=None, max=None):
		lookers = lookers if lookers else []
		found = False
		sendCount = 0
		for mobile in self.mobiles:
			if condition(mobile):
				mobile.sendToClient(message.format(*[sender.getName(mobile) for sender in lookers]))
				found = True
				if max:
					sendCount += 1
					if sendCount >= max:
						return found
		return found

	def sendToBufferCondition(self, condition, message, lookers=None):
		lookers = lookers if lookers else []
		found = False
		for mobile in self.mobiles:
			if condition(mobile):
				mobile.sendToBuffer(message.format(*[sender.getName(mobile) for sender in lookers]))
				found = True
		return found

	def getPlayerById(self, playerId):
		matches = [mobile for mobile in self.mobiles if mobile.id == playerId]

		return matches[0] if len(matches) > 0 else False

	def registerPlayer(self, client, playerData):
		playerId = playerData['_id']

		# See if playerId is in game.
		candidatePlayer = self.getPlayerById(playerId)

		if candidatePlayer:
			# If candidate is linkdead, reconnect
			if candidatePlayer.isLinkdead():
				print 'Reconnecting to player {name}'.format(name=candidatePlayer.name)
				candidatePlayer.client = client
				candidatePlayer.sendToClient('Reconnecting.')
				candidatePlayer.processCommand('look')
				candidatePlayer.linkdead = 0

				# And return candidatePlayer to attach to the browser
				return candidatePlayer
			else:
				return False
		else:
			# Make a new mobile
			name = playerData['name']

			newMobile = Mobile(name, self, {'charClass': 'warrior'})
			newMobile.client = client
			self.mobiles.append(newMobile)

			newMobile.id = playerId

			if 'room' in playerData:
				newMobile.room = self.rooms[playerData['room']]
			else:
				newMobile.room = self.rooms[0]
			if 'stats' in playerData:
				for stat in playerData['stats']:
					newMobile.stats[stat] = playerData['stats'][stat]

			newMobile.sendToClient('@uWelcome to Redemption, {name}@x.'.format(name=newMobile.name))
			return newMobile

	def checkName(self, name):
		sameName = [mobile for mobile in self.mobiles if mobile.name.lower() == name.lower()]
		return not len(sameName)

	def loadMobiles(self):
		mobiles = [mobile for mobile in self.db.mobiles.find({'user_id': { '$exists': False }} )]
		self.mobile_list = {}
		for i in range(0, len(mobiles)):
			self.mobile_list[str(mobiles[i]['_id'])] = mobiles[i]

	def loadItems(self):
		items = [item for item in self.db.items.find()]
		self.items = {}
		for i in range(0, len(items)):
			self.items[str(items[i]['_id'])] = Item(items[i])

	def loadRooms(self):
		import copy

		rooms = self.db.rooms.find()
		for i in range(0, rooms.count()):   # default is zero
			newRoom = Room(self, rooms[i])
			print newRoom
			print rooms[i]
			newRoom.id = rooms[i]['id']
			if 'items' in rooms[i]:
				for item in rooms[i]['items']:#
					newRoom.items.append(copy.deepcopy(self.items[item]))

			if 'npcs' in rooms[i]:
				for mobile in rooms[i]['npcs']:
					m = Mobile(self.mobile_list[mobile]['name'], self, self.mobile_list[mobile])
					m.room = newRoom
					self.mobiles.append(m)

			self.rooms.append(newRoom)

		# have to load all the rooms BEFORE loading the exits
		for i in range(0, rooms.count()):
			exits = rooms[i]['exits']
			for e in exits:
				exit = exits[e]
				target_room = next(room for room in self.rooms if room.id == exit['target'])
				direction = exit['direction']
				self.rooms[i].exits.append(Exit(direction.lower(), target_room))

	def simpleInit(self):
		self.loadItems() # loads item 'prototypes'
		self.loadMobiles()
		self.loadRooms()
		"""
		self.rooms.append(Room(self, 'The Temple of Bosco'))
		self.rooms.append(Room(self, 'Temple Square'))
		self.rooms.append(Room(self, 'Entrance to the Boar\'s Head Inn'))
		self.rooms.append(Room(self, 'At The Temple Altar'))
		self.rooms.append(Room(self, 'Market Square'))

		self.rooms[0].exits.append(Exit('south', self.rooms[1]))
		self.rooms[0].exits.append(Exit('north', self.rooms[3]))

		self.rooms[1].exits.append(Exit('north', self.rooms[0]))
		self.rooms[1].exits.append(Exit('east', self.rooms[2]))
		self.rooms[1].exits.append(Exit('south', self.rooms[4]))

		self.rooms[2].exits.append(Exit('west', self.rooms[1]))

		self.rooms[3].exits.append(Exit('south', self.rooms[0]))

		self.rooms[4].exits.append(Exit('north', self.rooms[1]))
		"""
		midgaard = Area(self, 'Midgaard')
		self.areas.append(midgaard)

		for room in self.rooms:
			room.area = midgaard

		"""
		self.rooms[0].items.append(
			Item({'name': 'a Bashball Bat', 'keywords': ['bashball', 'bat'], 'wear': 'weapon', 'noun': 'bash', 'roll': 7, 'stats': {}}))
		self.rooms[0].items.append(
			Item({'name': 'the Second Hand', 'keywords': ['second', 'hand', 'sword'], 'wear': 'weapon', 'noun': 'stab', 'roll': 10, 'stats': {}}))
		self.rooms[1].items.append(
			Item({'name': 'a kitten named Ruby', 'keywords': ['kitten', 'cat', 'ruby'], 'stats': {}}))
		

		self.mobiles.append(Mobile('a Fungusaur', self, {'keywords': ['fungusaur', 'monster']}))
		self.mobiles.append(Mobile('a Fungusaur', self, {'keywords': ['fungusaur', 'monster']}))
		self.mobiles.append(Mobile('a Fungusaur', self, {'keywords': ['fungusaur', 'monster']}))

		self.mobiles[0].room = self.rooms[0]
		self.mobiles[1].room = self.rooms[1]
		self.mobiles[2].room = self.rooms[1]
		"""
		craftingInit(self)