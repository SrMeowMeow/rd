import combat
from mobile import Mobile
from room import Room
from exit import Exit
from area import Area
from item import Item
from mobile import Mobile
from interpreters.crafting import craftingRecipe
from lib.interpreters.constants import Range
import utility
import datetime

import lib.save as save
import thread

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

		self.startTime = datetime.datetime.now()

		self.clock = 0
		self.combatInterval = 0
		self.gameUpdateInterval = 0
		self.repopInterval = 0

		self.interval = 0.1

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

		targets = []

		for potentialTarget in potentialTargets:
			for keyword in potentialTarget.keywords:
				if keyword.lower().startswith(targetName.lower()):
					targets.append(potentialTarget)
					continue

		if not targets:
			return False

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
		self.combatInterval += self.interval
		self.gameUpdateInterval += self.interval
		self.repopInterval += self.interval

		# Restore charges
		if self.clock % 6 * self.interval == 0:
			print ' - Charge Update ' + str(datetime.datetime.now().time())
			for mobile in [m for m in self.mobiles if m.getStat('charges') < m.getStat('maxcharges')]:
				mobile.setStat('charges', mobile.getStat('charges') + 1)

		for mobile in self.mobiles:
			mobile.update(self.interval)

		if self.combatInterval > 2:
			print ' - Combat Update ' + str(datetime.datetime.now().time())
			self.combatInterval = 0
			combat.doGlobalRound(self)

		if self.gameUpdateInterval > 10:
			self.gameUpdateInterval = 0
			latency = ( ( datetime.datetime.now() - self.startTime ).seconds - self.clock ) / self.clock
			print 'Game Update {time} : {latency}'.format(time=str(datetime.datetime.now().time()),latency=latency)

		#repop!  -> every 3 minutes?
		if self.repopInterval > 180:
			self.repopInterval = 0
			print 'autosaving players'
			for mobile in self.mobiles:
				if mobile.is_player:
					dbd = save.databaseDaemon()
					thread.start_new_thread(dbd.saveMobile, (mobile,))
			self.repopulate()

		Timer(self.interval, self.updateGame).start()

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
				print '{name} has reconnected.'.format(name=candidatePlayer.name)
				candidatePlayer.client = client
				candidatePlayer.sendToClient('Reconnecting.')
				candidatePlayer.linkdead = 0

				for mobile in [mobile for mobile in self.mobiles if mobile is not candidatePlayer]:
					mobile.sendToClient('@g{name} has reconnected.@x'.format(name=candidatePlayer.getName(mobile)))

				# And return candidatePlayer to attach to the browser
				return candidatePlayer
			else:
				return False
		else:
			# Make a new mobile
			name = playerData['name'].capitalize()
			stats = playerData['stats'] if 'stats' in playerData else {}

			newMobile = Mobile(name, self, {'stats': stats})
			newMobile.client = client
			newMobile.is_player = True
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

			for mobile in [mobile for mobile in self.mobiles if mobile is not newMobile]:
				mobile.sendToClient('@g{name} has connected.@x'.format(name=newMobile.getName(mobile)))

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
			self.items[str(items[i]['_id'])] = items[i]

	def loadRecipes(self):
		recipes = [recipe for recipe in self.db.recipes.find()]
		self.recipes = []
		for recipe in recipes:
			newRecipe = craftingRecipe(recipe['name'])
			newRecipe.product = self.items[recipe['product']] if recipe['product'] in self.items else None
			for ingredient in recipe['ingredients']:
				if ingredient in self.items:
					newRecipe.ingredients.append(self.items[ingredient])
			self.recipes.append(newRecipe)

	def loadRooms(self):
		rooms = self.db.rooms.find()
		for i in range(0, rooms.count()):   # default is zero
			exists = [r for r in self.rooms if r.id == rooms[i]['id']]
			if len(exists) > 0:
				newRoom = exists[0]
				newRoom.bg = rooms[i]['bg'] if 'bg' in rooms[i] else newRoom.bg
				newRoom.desc = rooms[i]['description'] if 'description' in rooms[i] else newRoom.desc
			else:
				newRoom = Room(self, rooms[i])
				newRoom.id = rooms[i]['id']

			if newRoom.bg:
				print "Has a background!", newRoom.bg

			newRoom.items = []
			newRoom.exits = []
			if 'items' in rooms[i]:
				for item in rooms[i]['items']:#
					newRoom.items.append(Item(self.items[item]))

			if 'npcs' in rooms[i]:
				# only respawn if there is NO combat going on in the room to avoid insane duplications! FIX ME
				currentMobiles = [mobile for mobile in self.mobiles if mobile.room == newRoom and mobile.combat and not mobile.is_player]
				if not len(currentMobiles) > 0:
					for mobile in rooms[i]['npcs']:
						m = Mobile(self.mobile_list[mobile]['name'], self, self.mobile_list[mobile])
						m.room = newRoom
						self.mobiles.append(m)

			if len(exists) <= 0:
				self.rooms.append(newRoom)

		# have to load all the rooms BEFORE loading the exits
		for i in range(0, rooms.count()):
			exits = rooms[i]['exits']
			for e in exits:
				exit = exits[e]
				target_room = next(room for room in self.rooms if room.id == exit['target'])
				direction = exit['direction']
				self.rooms[i].exits.append(Exit(direction.lower(), target_room))

	def repopulate(self):
		self.loadItems()
		self.loadMobiles()
		# reload all mobiles except for players, and those in combat
		self.mobiles = [mobile for mobile in self.mobiles if mobile.is_player or mobile.combat]
		[mobile.sendToClient('Something flickers.') for mobile in self.mobiles]
		self.loadRooms()

	def simpleInit(self):
		self.loadItems() # loads item 'prototypes'
		self.loadMobiles()
		self.loadRooms()
		self.loadRecipes()
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

		#craftingInit(self)