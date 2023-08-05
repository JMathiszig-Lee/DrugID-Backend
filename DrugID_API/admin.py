from django.contrib import admin
from django.apps import apps
from DrugID_API.models import Result
from import_export import resources
from import_export.admin import ExportActionModelAdmin

# Register your models here.
class ListAdminMixin(object):
    def __init__(self, model, admin_site):
        self.list_display = [field.name for field in model._meta.fields]
        super(ListAdminMixin, self).__init__(model, admin_site)

class ResultResource(resources.ModelResource):
    class Meta:
        model = Result


    
models = apps.get_models()
for model in models:
    admin_class = type('AdminClass', (ListAdminMixin, admin.ModelAdmin), {})
    try:
        admin.site.register(model, admin_class)
    except admin.sites.AlreadyRegistered:
        pass

class CustomResultAdmin(ExportActionModelAdmin, admin.ModelAdmin):
    resource_classes = [ResultResource]
    pass