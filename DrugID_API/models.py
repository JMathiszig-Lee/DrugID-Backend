from django.db import models

# Create your models here.

# User Details
class User(models.Model):
	email = models.EmailField(max_length=75)
	SPECIALITY_CHOICES = [
		('GAS', 'Anaesthetics'),
		('A+E', 'Emergency Medicine'),
		('ICM', 'Intensive Care'),
		('OTH', 'Other')
	]
	speciality = models.CharField(
		max_length=3,
		choices= SPECIALITY_CHOICES,
		default='GAS')
	years_experience = models.IntegerField(max_length=2, null=True)


# Drug labeling group
class Group(models.IntegerChoices):
		pharma = 1
		ISO = 2
		black_white = 3

# User session
class Session(models.Model):
	user_id = models.ForeignKey(User, on_delete=models.CASCADE)
	last_group = models.IntegerField(choices = Group.choices)

# Drug data
class Drug(models.Model):
	name = models.CharField(max_length=100)

# Drug asset
class Asset(models.Model):
	drug_id = models.ForeignKey(Drug, on_delete=models.CASCADE)
	asset_url = models.CharField(max_length=200)
	group = models.IntegerField(choices = Group.choices)

# Set data
class Set(models.Model):
	group =  models.IntegerField(choices = Group.choices)
	asset_id = models.ForeignKey(Asset, on_delete=models.CASCADE)
	target = models.ForeignKey(Drug, on_delete=models.CASCADE)
	time_limit = models.IntegerField()


# Results of test
class Result(models.Model):
	set_id = models.ForeignKey(Set, on_delete=models.CASCADE, null=True)
	time = models.CharField(max_length=20)
	selected = models.CharField(max_length=100)
	correct = models.BooleanField()
	sequence_id = models.CharField(max_length=100)
	session_id = models.ForeignKey(Session, on_delete=models.CASCADE)
	group =  models.IntegerField(choices = Group.choices)
