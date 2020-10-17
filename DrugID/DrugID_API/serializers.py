from rest_framework import serializers

from .models import asset


class AssetSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = asset
        fields = 