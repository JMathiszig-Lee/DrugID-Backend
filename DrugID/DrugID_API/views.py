from django.shortcuts import render

from rest_framework import viewsets
from models import Asset, 

import os
import random

# Create your views here.

class DrugSetViewSet(viewsets.ReadOnlyModelViewSet):
    #basic view to display list of drugs

    #get number of drugs to return but default is 8
    numdrugs =int(os.getenv('NUMBER_DRUGS', 8))

    #select n random drugs
    #TODO this method is potentially slow and may need updating
    drugs = Asset.objects.all().order_by('?').filter(Group=2)[:numdrugs]

    target = random.choice(drugs)