import re


# utility functions
def match(search, target):
	return re.match(search, target, re.I)


def matchList(search, listOfTargets):
	for target in listOfTargets:
		result = re.match(search, target, re.I)
		if result:
			return result
	return False
