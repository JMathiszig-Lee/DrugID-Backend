from rest_framework import serializers

from DrugID_API.models import Participant


class MagicLinkRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    speciality = serializers.ChoiceField(choices=Participant.SPECIALITY_CHOICES)
    years_experience = serializers.IntegerField(min_value=0, max_value=80)

    def validate_email(self, value):
        return value.strip().lower()


class ReturningMagicLinkRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)

    def validate_email(self, value):
        return value.strip().lower()


class MagicLinkVerifySerializer(serializers.Serializer):
    token = serializers.CharField(min_length=20, max_length=512, trim_whitespace=True)


class TrialResultInputSerializer(serializers.Serializer):
    selected_asset_id = serializers.IntegerField(min_value=1, allow_null=True)
    response_time_ms = serializers.IntegerField(min_value=0, max_value=600_000)
