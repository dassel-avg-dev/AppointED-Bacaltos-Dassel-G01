from django.db import migrations

TYPES = ["Consultation", "Advising", "Clearance", "Document Request"]


def seed(apps, schema_editor):
    AppointmentType = apps.get_model("scheduling", "AppointmentType")
    for name in TYPES:
        AppointmentType.objects.get_or_create(type_name=name)


class Migration(migrations.Migration):
    dependencies = [("scheduling", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
