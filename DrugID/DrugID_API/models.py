from django.db import models

# Create your models here.

# User Details
class User(models.Model):
	email = models.EmailField(max_length=75)

# Drug labeling group
class Group(model.Model):

	class group(models.IntegerChoices):
		pharma = 1
		ISO = 2
		black_white = 3

# User session
class Session(models.Model):
	#session_id = models.CharField(max_length=100)
	user_id = models.ForeignKey(User.id)
	last_group = models.IntergerField()

# Drug data
class Drug(models.Model):
	#drug_id = models.CharField(max_length=10)
	name = models.CharField(max_length=100)

# Drug asset
class Asset
	drug_id = model.ForeignKey(Drug.id)
	asset_url = models.CharField(max_length=200)
	group = models.ForeignKey(Group.group)

# Set data
class Set:
	group = models.ForeignKey(Group.group)
	asset_id = models.ForeignKey(Asset.id)
	target = model.ForeignKey(Drug.id)
	time_limit = models.IntergerField()


# Results of test
class Result:
	#set_id = models.CharField(max_length = 100)
	time = models.TimeField()
	correct = BooleanField()
	sequence_id = models.CharField(max_length=100)
	session_id = models.ForeignKey(Session.id) # check
	group = models.ForeignKey(group.id)
