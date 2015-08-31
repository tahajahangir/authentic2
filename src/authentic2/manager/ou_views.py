from django_rbac.utils import get_ou_model
from django.http import HttpResponseRedirect
from django.contrib import messages
from django.utils.translation import ugettext as _

from . import tables, views, forms


class OrganizationalUnitView(views.BaseTableView):
    template_name = 'authentic2/manager/ous.html'
    model = get_ou_model()
    table_class = tables.OUTable
    search_form_class = forms.NameSearchForm
    permissions = ['a2_rbac.view_organizationalunit']

listing = OrganizationalUnitView.as_view()


class OrganizationalUnitAddView(views.BaseAddView):
    model = get_ou_model()
    fields = ['name', 'slug', 'email_is_unique', 'username_is_unique']
    permissions = 'a2_rbac.add_organizationalunit'

    def get_success_url(self):
        return '..'

add = OrganizationalUnitAddView.as_view()


class OrganizationalUnitEditView(views.BaseEditView):
    model = get_ou_model()
    fields = ['name', 'slug', 'email_is_unique', 'username_is_unique']
    permissions = ['a2_rbac.change_ou']

edit = OrganizationalUnitEditView.as_view()


class OrganizationalUnitDeleteView(views.BaseDeleteView):
    model = get_ou_model()
    template_name = 'authentic2/manager/ou_delete.html'
    permissions = ['a2_rbac.delete_ou']

    def dispatch(self, request, *args, **kwargs):
        if self.get_object().default:
            messages.warning(request, _('You cannot delete the default '
                                        'organizational unit, you must first '
                                        'set another default organiational '
                                        'unit.'))
            return self.return_ajax_response(
                request, HttpResponseRedirect(self.get_success_url()))
        return super(OrganizationalUnitDeleteView, self).dispatch(request, *args,
                                                                  **kwargs)


delete = OrganizationalUnitDeleteView.as_view()
