from django import forms
from apps.rooms.models import MeterReading, Room

class MeterReadingForm(forms.ModelForm):
    class Meta:
        model = MeterReading
        fields = ['room', 'reading_date', 'water_prev', 'water_curr', 'elec_prev', 'elec_curr', 'water_photo', 'elec_photo']
        widgets = {
            'reading_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        dormitory = kwargs.pop('dormitory', None)
        super().__init__(*args, **kwargs)
        if dormitory:
            self.fields['room'].queryset = Room.objects.filter(floor__building__dormitory=dormitory)
        
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-control'})


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['floor', 'number', 'status', 'base_rent']

    def __init__(self, *args, **kwargs):
        dormitory = kwargs.pop('dormitory', None)
        super().__init__(*args, **kwargs)
        if dormitory:
            from apps.rooms.models import Floor
            self.fields['floor'].queryset = Floor.objects.filter(building__dormitory=dormitory)
        
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-control'})
