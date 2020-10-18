from rest_framework import serializers

from DrugID_API.models import Asset, Set, Result, Session, User


class SetSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Set
        fields = ['group', 'asset_id', 'target', 'time_limit']

class ResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = Result
        fields = ['set_id', 'time', 'selected', 'correct', 'sequence_id', 'session_id', 'group']

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'speciality', 'years_experience']