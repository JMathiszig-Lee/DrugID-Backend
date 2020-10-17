from django.core.management.base import BaseCommand, CommandError
#from models import asset, drug
import os
class Command(BaseCommand):
    help = "goes through assets folder and inserts into database"

    def handle(self, *args, **options):
        # try:
        #     for filename in os.listdir("./assets"):
        #         print(filename)
        # except:
        #     raise CommandError("broken :(")
        folders = ["iso", "blackwhite", "industry"]
        names = {}
        for fold in folders:
            names[fold] = []
            for filename in os.listdir("./DrugID_API/assets/" + fold):
                names[fold].append(filename)

        for name in names["iso"]:
            if name in names["blackwhite"]:
                if name in names["industry"]:
                    print(name + " passes")
                    #insert into database here
                else:
                    print(name + " missing in industry")
            else:
                print(name + " missing in black and white")