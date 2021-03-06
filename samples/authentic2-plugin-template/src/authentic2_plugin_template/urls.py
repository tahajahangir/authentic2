from django.conf.urls import url

from authentic2.decorators import setting_enabled, required

from . import app_settings
from .views import index

urlpatterns = required(
        setting_enabled('ENABLE', settings=app_settings),
        [url('^authentic2_plugin_template/$', index, name='authentic2-plugin-template-index')]
)
