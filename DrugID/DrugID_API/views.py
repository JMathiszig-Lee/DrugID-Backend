from django.shortcuts import render

from rest_framework import viewsets
from models import *

import os
import random

# Create your views here.

class DrugSetViewSet(viewsets.ReadOnlyModelViewSet):
    #basic view to display list of drugs

    #get number of drugs to return but default is 8
    numdrugs =int(os.getenv('NUMBER_DRUGS', 8))

    drugs = assets.objects.all().order_by('?').filter(group=1)[:numdrugs]

    target = random.choice(drugs)