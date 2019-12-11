# -*- coding: utf8 -*-
#
#    Copyright (C) 2018 NDP Systèmes (<http://www.ndp-systemes.fr>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import logging

import openerp
from openerp import models, exceptions

_logger = logging.getLogger(__name__)


def is_module_installed(env, module_name):
    """ Check if an Odoo addon is installed.

    :param module_name: name of the addon
    """
    # the registry maintains a set of fully loaded modules so we can
    # lookup for our module there
    return module_name in env.registry._init_modules


UNLINK_ORIGINAL = models.BaseModel.unlink


@openerp.api.multi
def get_non_synchronized_items(self):
    if is_module_installed(self.env, 'bus_integration'):
        receive_transfer = self.env['bus.receive.transfer'].sudo().search([('model', '=', self._name),
                                                                           ('local_id', '=', self.ids)])
        return self.env[self._name].search([('id', 'in', self.ids),
                                            ('id', 'not in', [item.local_id for item in receive_transfer])])
    return self


@openerp.api.multi
def unlink_bus(self):
    if is_module_installed(self.env, 'bus_integration'):
        receive_transfer = self.env['bus.receive.transfer'].sudo().search([('model', '=', self._name),
                                                                           ('local_id', 'in', self.ids)])
        mapping = self.env['bus.object.mapping'].search([('model_name', '=', self._name)], limit=1)
        not_deletable_ids = [item.local_id for item in receive_transfer]
        if receive_transfer and mapping and not mapping.deactivate_on_delete:
            _logger.info(u"Object(s) %s with IDs %s can not be deleted. They are synchronized (%s) and their mapping is"
                         u" configured without 'deactivate on delete' (%s)",
                         self._name, not_deletable_ids, receive_transfer, mapping)
            raise exceptions.except_orm(u"Bus Error", u"Impossible to delete record on synchronized records %s, IDs=%s"
                                                      u", please deactivate the record in the sending instance" %
                                        (self._name, not_deletable_ids))
    res_unlink = UNLINK_ORIGINAL(self)
    return res_unlink


models.BaseModel.unlink = unlink_bus
models.BaseModel.get_non_synchronized_items = get_non_synchronized_items

FIELDS_GET_ORIGINAL = models.BaseModel.fields_get


@openerp.api.model
def fields_get_bus(self, allfields=None, context=None, write_access=True, attributes=None):
    """
    Override to inform is the field si imported or exported and set readonly if update is prohibited when import
    ⇐ : &lArr;
    ⇒ : &rArr;
    """
    res = FIELDS_GET_ORIGINAL(self, allfields=allfields, context=context, write_access=write_access,
                              attributes=attributes)
    if is_module_installed(self.env, 'bus_integration'):
        mapping_fields = self.env['bus.object.mapping.field'].search([('mapping_id.model_name', '=', self._name)])
        for mapping_field in mapping_fields:
            if mapping_field.field_name in res:
                if mapping_field.mapping_id.is_exportable:
                    res[mapping_field.field_name]['string'] = u"⇐ %s" % (res[mapping_field.field_name]['string'])
                elif mapping_field.mapping_id.is_importable:
                    res[mapping_field.field_name]['string'] = u"⇒ %s" % (res[mapping_field.field_name]['string'])
    return res


models.BaseModel.fields_get = fields_get_bus
