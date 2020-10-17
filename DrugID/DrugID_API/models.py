from django.db import models

# Create your models here.

# User Details
class User(models.Model):
	user_id = models.CharField(max_length=100)
	email = models.EmailField(max_length=75)

# Drug labeling group
class Group(models.Model):

	class Group(models.IntegerChoices):
		pharma = 1
		ISO = 2
		black_white = 3

# User session
class Session(models.Model):
	session_id = models.CharField(max_length=100)
	user_id = models.CharField(max_length=100)
	#last_group = models.IntergerField()

# Drug data
class Drug(models.Model):
	drug_id = models.CharField(max_length=10)
	name = models.CharField(max_length=100)

# Drug asset
class Asset(models.Model):
	drug_id = models.CharField(max_length=10)
	asset_url = models.CharField(max_length=200)

	class Group(models.IntegerChoices):
		pharma = 1
		ISO = 2
		black_white = 3

# ??
class Set:

	class Group(models.IntegerChoices):
		pharma = 1
		ISO = 2
		black_white = 3

# Result data
class Result:
	set_id = models.CharField(max_length = 100)
	time = models.TimeField()
	#correct = BooleanField()
	sequence_id = models.CharField(max_length=100)
	session_id = models.CharField(max_length=100)
