# DrugID-Backend

## Install/Get started
pipenv install
pipenv shell
cd DrugID/
python manage.py migrate
python manage.py insert_assets
python manage.py createsuperuser
python manage.py runserver