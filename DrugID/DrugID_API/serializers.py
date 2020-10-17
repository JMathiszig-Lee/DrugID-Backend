from rest_framework import serializers

from DrugID_API.models import Asset, Set, Result, Session


class SetSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Set
        fields = ['group', 'asset_id', 'target', 'time_limit']

class ResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = Result
        fields = ['time', 'correct', 'sequence_id', 'session_id', 'session_id', 'group']