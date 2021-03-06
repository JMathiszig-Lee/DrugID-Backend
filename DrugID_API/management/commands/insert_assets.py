from pathlib import Path

from django.core.management.base import BaseCommand
from DrugID_API.models import Asset, Drug

import os


class Command(BaseCommand):
    def handle(self, *args, **options):

        label_types = ["industry", "iso", "blackwhite"]

        # Populates the Drug table
        names_drug = os.listdir(Path("DrugID_API/static/industry"))
        for name in names_drug:
            nm = name[:-4]
            data_input_drug = Drug(name=nm)
            data_input_drug.save()

        # loop through 3 types populating the Asset table
        for type in label_types:
            # Directory for each type > 'DrugID_API/assets/' for release > '../../assets/' for debugging
            label_type_directory = "DrugID_API/static/" + type + "/"

            # put all assets names for type in array
            label_array = os.listdir(Path(label_type_directory))

            # Input individual lables for label type
            for name_label in label_array:
                # Shortens label name to remove file extension and inserts data into Drug table
                n = name_label[:-4]
                # print(n) debugging
                # Selects data from last entry made in Drug table
                drug = Drug.objects.get(name=n)
                #print(drug.id) debugging

                # creates directory for database
                path = "static/" + type + "/" + name_label
                # print(path) debugging

                # creates code depending on the label type
                if type == "industry":
                    group_id = 1
                elif type == "iso":
                    group_id = 2
                elif type == "blackwhite":
                    group_id = 3

                # Inserts Data into table
                data_input_asset = Asset(drug_id=drug, asset_url=path, group=group_id)
                data_input_asset.save()
