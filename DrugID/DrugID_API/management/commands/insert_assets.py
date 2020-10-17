from django.core.management.base import BaseCommand, CommandError
from DrugID_API.models import Asset, Drug

import os
class Command(BaseCommand):
    help = "goes through assets folder and inserts into database"

    def handle(self, *args, **options):
        # try:
        #     for filename in os.listdir("./assets"):
        #         print(filename)
        # except:
        #     raise CommandError("broken :(")
        folders = ["industry", "iso", "blackwhite"]
        names = {}
        for fold in folders:
            names[fold] = []
            for filename in os.listdir("./DrugID_API/assets/" + fold):
                names[fold].append(filename)

        def insert_asset(drugfile):
            drugname = drugfile[:-4]
            d = Drug(name = drugname)
            d.save()
            drug = Drug.objects.get(name = drugname)[:1]
            print(drug)

            for group, fold in enumerate(folders, 1):
                path = fold + "/" + drugfile
                a = Asset(drug_id = drug.ID, asset_url = path, Group = group )
                a.save()

        for name in names["iso"]:
            if name in names["blackwhite"]:
                if name in names["industry"]:
                    print(name + " passes")
                    insert_asset(name)
                else:
                    print(name + " missing in industry")
            else:
                print(name + " missing in black and white")


        