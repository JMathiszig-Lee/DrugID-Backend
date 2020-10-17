from pathlib import Path

from django.core.management.base import BaseCommand
from DrugID_API.models import Asset, Drug

import os
class Command(BaseCommand):

    label_types = ["industry", "iso", "blackwhite"]

    label_array = {}

    # loop through 3 types
    for type in label_types:
        # Directory for each type
        label_type_directory = "DrugID_API/assets/"

        # put all assets names for type in array
        label_array = os.listdir(Path(label_type_directory))

        # Input individual lables for label type
        for name_label in label_array:
            # Shortens label name to remove file extension and inserts data into Drug table
            n = name_label[:-4]
            data_input_drug = Drug(name = n)
            data_input_drug.save()

            drug = Drug(name = n)
            print(drug.id)

            # creates directory for database
            path = "assets/" + type + "/" + name_label
            # creates code depending on the label type
            if(type == "industry" ):
                group_id = 1
            elif(type == "iso"):
                group_id = 2
            elif(type == "backwhite"):
                group_id = 3

            # Inserts Data into table
            data_input_asset = Asset(drug_id = drug.id, asset_url = path, group = group_id)
            data_input_asset.save()






