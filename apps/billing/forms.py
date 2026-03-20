from django import forms
from apps.billing.models import BillingSettings

class BillingSettingsForm(forms.ModelForm):
    class Meta:
        model = BillingSettings
        fields = ['bill_day', 'grace_days', 'elec_rate', 'water_rate', 'tmr_api_key', 'tmr_secret', 'dunning_enabled']
        widgets = {
            'tmr_secret': forms.PasswordInput(render_value=True),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})
        self.fields['dunning_enabled'].widget.attrs.update({'class': 'form-check-input'})
