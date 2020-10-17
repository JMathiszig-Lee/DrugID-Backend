from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions

from DrugID_API.models import Asset, Drug, Set, Result
from DrugID_API.serializers import ResultSerializer

import os
import random

# Create your views here.
@permission_classes((permissions.AllowAny,))
class DrugSet(APIView):
    #basic view to display list of drugs


    def get(self, request, format=None):
        #get number of drugs to return but default is 8
        numdrugs =int(os.getenv('NUMBER_DRUGS', 8))
        limit =int(os.getenv('TIME_LIMIT', 3000))
        #select n random drugs
        #TODO this method is potentially slow and may need updating
        drugs = Asset.objects.all().order_by('?').filter(group=2)[:numdrugs]
        drugslist = []
        for i in drugs:
            drugslist.append(i)
        #target = random.choice(drugs)
        target = "adrenaline"
        payload = {
            "set_id": "fixed",
            "ampoules": drugslist,
            "target_drug": target,
            "time_limit": limit
        }
        #save as a set
        return Response(payload)

class ResultsViewSet(viewsets.ModelViewSet):
    """
    Simple results viewset
    """

    queryset = Result.objects.all()
    serializer_class = ResultSerializer
