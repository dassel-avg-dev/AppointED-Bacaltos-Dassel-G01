from django.db import migrations

DEPARTMENTS = [
    "College of Computer Studies",
    "College of Engineering",
    "College of Business",
    "Registrar",
    "Guidance Office",
]


def seed(apps, schema_editor):
    Department = apps.get_model("accounts", "Department")
    for name in DEPARTMENTS:
        Department.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
