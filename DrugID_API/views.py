from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework import permissions

from DrugID_API.models import Asset, Drug, Set, Result, Session, User
from DrugID_API.serializers import ResultSerializer, UserSerializer

import os
import random
import socket

# Create your views here.
@permission_classes((permissions.AllowAny,))
class DrugSet(APIView):
    #basic view to display list of drugs


    def get(self, request, format=None):
        #get number of drugs to return but default is 8
        numdrugs =int(os.getenv('NUMBER_DRUGS', 8))

        #Set time limit
        limit =int(os.getenv('TIME_LIMIT', 3000))

        #get group from request session
        session_id = request.GET.get('session_id')
        session = Session.objects.get(id=session_id)

        #get local hostname 
        try:
            HOSTNAME = request.META['HTTP_HOST']
        except:
            HOSTNAME = 'localhost'

        #select n random drugs
        #TODO this method is potentially slow and may need updating
        drugs = Asset.objects.all().order_by('?').filter(group=session.last_group)[:numdrugs]
        drugslist = []

        
        for i in drugs:
            #s.asset_id.add(i)
            drugslist.append({
                "Id": i.drug_id.name, 
                "ImageSrc":request.META['wsgi.url_scheme'] + "://" + HOSTNAME + "/" + i.asset_url,
                })
        
        target = random.choice(drugs)
        s = Set(group=session.last_group, target=target.drug_id, time_limit=limit)
        s.save()
        s.asset_id.set(drugs)
        s.save()

        payload = {
            "SetId": s.id,
            "Ampoules": drugslist,
            "TargetDrug": target.drug_id.name,
            "TimeLimit": limit,
            "Group": session.last_group
        }
        #save as a set
        
        return Response(payload)

@permission_classes((permissions.AllowAny,))
class ResultsViewSet(viewsets.ModelViewSet):
    """
    Simple results viewset
    """

    queryset = Result.objects.all()
    serializer_class = ResultSerializer

class UserViewSet(viewsets.ModelViewSet):
    """
    Simple User viewset
    """

    queryset = User.objects.all()
    serializer_class = UserSerializer

