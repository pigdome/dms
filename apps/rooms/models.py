from django.db import models
from apps.core.models import Dormitory, CustomUser


class Building(models.Model):
    dormitory = models.ForeignKey(Dormitory, on_delete=models.CASCADE, related_name='buildings')
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.dormitory.name} - {self.name}'


class Floor(models.Model):
    building = models.ForeignKey(Building, on_delete=models.CASCADE, related_name='floors')
    number = models.PositiveIntegerField()

    class Meta:
        ordering = ['number']
        unique_together = ['building', 'number']

    def __str__(self):
        return f'{self.building.name} Floor {self.number}'


class Room(models.Model):
    class Status(models.TextChoices):
        OCCUPIED = 'occupied', 'Occupied'
        VACANT = 'vacant', 'Vacant'
        CLEANING = 'cleaning', 'Cleaning'
        MAINTENANCE = 'maintenance', 'Maintenance'

    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name='rooms')
    number = models.CharField(max_length=20)
    base_rent = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.VACANT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['floor', 'number']

    def __str__(self):
        return f'Room {self.number} - {self.floor}'

    @property
    def dormitory(self):
        return self.floor.building.dormitory


class MeterReading(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='meter_readings')
    water_prev = models.DecimalField(max_digits=10, decimal_places=2)
    water_curr = models.DecimalField(max_digits=10, decimal_places=2)
    water_photo = models.ImageField(upload_to='meters/water/', blank=True, null=True)
    elec_prev = models.DecimalField(max_digits=10, decimal_places=2)
    elec_curr = models.DecimalField(max_digits=10, decimal_places=2)
    elec_photo = models.ImageField(upload_to='meters/elec/', blank=True, null=True)
    recorded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    reading_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-reading_date']

    def __str__(self):
        return f'Meter {self.room} - {self.reading_date}'

    @property
    def water_units(self):
        return self.water_curr - self.water_prev

    @property
    def elec_units(self):
        return self.elec_curr - self.elec_prev
