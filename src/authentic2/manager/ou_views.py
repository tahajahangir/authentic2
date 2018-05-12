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
    permissions = ['a2_rbac.search_organizationalunit']
    title = _('Organizational units')

listing = OrganizationalUnitView.as_view()


class OrganizationalUnitAddView(views.BaseAddView):
    model = get_ou_model()
    permissions = ['a2_rbac.add_organizationalunit']
    form_class = forms.OUEditForm
    title = _('Add organizational unit')

    def get_success_url(self):
        return '..'

add = OrganizationalUnitAddView.as_view()


class OrganizationalUnitDetailView(views.BaseDetailView):
    model = get_ou_model()
    permissions = ['a2_rbac.view_organizationalunit']
    form_class = forms.OUEditForm
    template_name = 'authentic2/manager/ou_detail.html'

    @property
    def title(self):
        return unicode(self.object)

    def authorize(self, request, *args, **kwargs):
        super(OrganizationalUnitDetailView, self).authorize(request, *args, **kwargs)
        self.can_delete = self.can_delete and not self.object.default

detail = OrganizationalUnitDetailView.as_view()


class OrganizationalUnitEditView(views.BaseEditView):
    model = get_ou_model()
    permissions = ['a2_rbac.change_organizationalunit']
    form_class = forms.OUEditForm
    template_name = 'authentic2/manager/ou_edit.html'
    title = _('Edit organizational unit')

edit = OrganizationalUnitEditView.as_view()


class OrganizationalUnitDeleteView(views.BaseDeleteView):
    model = get_ou_model()
    template_name = 'authentic2/manager/ou_delete.html'
    permissions = ['a2_rbac.delete_organizationalunit']
    title = _('Delete organizational unit')

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
