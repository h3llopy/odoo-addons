# -*- coding: utf8 -*-
#
#    Copyright (C) 2017 NDP Systèmes (<http://www.ndp-systemes.fr>).
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
import json
from openerp import models, api


class BusSynchronizationMapper(models.AbstractModel):
    _name = 'bus.mapper'

    @api.model
    def process_mapping(self, record, record_model, external_key, model_mapping, message, odoo_record):
        error = []
        binding_data = {
            'model': record_model,
            'external_key': external_key,
            'received_data': json.dumps(record, indent=4),
            'origin_base_id': message.get_base_origin().id,
        }
        record_data = {}

        importable_fields = []
        required_fields = []
        for field in model_mapping.field_ids:
            if (field.import_creatable_field and not odoo_record) or (field.import_updatable_field and odoo_record):
                importable_fields.append(field.map_name)
                if field.field_id.required:
                    required_fields.append(field.map_name)
        if not importable_fields:
            error_message = u"Error no field to import for %s, id:%s, external_key:%s" % \
                            (record_model, record.get('id'), external_key)
            return binding_data, {}, [('error', error_message)]
        # add keys needed by bus to avoid warnings 'field %s not configured for import'
        importable_fields.append('xml_id')
        importable_fields.append('id')
        importable_fields.append('translation')
        importable_fields.append('external_key')
        importable_fields.append('bus_sender_id')
        importable_fields.append('bus_recipient_id')
        importable_fields.append('write_date')
        importable_fields.append('display_name')
        for field_key in record.keys():
            if field_key not in importable_fields:
                error.append(('warning', u"Field %s not configured for import" % field_key))
            elif field_key in required_fields and field_key not in record.keys():
                error.append(('error', u"Field %s is required, record id : %s" % (field_key, record.get('id'))))
            else:
                if isinstance(record.get(field_key), dict):
                    relational_values = False
                    model = record.get(field_key).get('model')
                    type_field = record.get(field_key).get('type_field')
                    if type_field == 'many2one':
                        needed_id = record.get(field_key).get('id')
                        relational_values = self.get_relational_value(model, needed_id, message.get_json_dependencies())
                    if type_field == 'many2many' or type_field == 'one2many':
                        needed_ids = record.get(field_key).get('ids')
                        relational_values = \
                            [(6, False, self.get_multiple_relational_value(model, needed_ids,
                                                                           message.get_json_dependencies()))]
                    record_data[field_key] = relational_values
                else:
                    record_data[field_key] = record.get(field_key)
        return binding_data, record_data, error

    @api.model
    def get_relational_value(self, model, id, dependencies):
        """ returns a local id of a relation or false
            :param model: model name aka: "stock.location"
            :param id: remote record id (id from the sender)
            :param dependencies: dict containing all models with all dependencies ids (remote, local and external_key)
        """
        model_deps = dependencies.get(model, {}).get(str(id))
        if 'bus_recipient_id' in model_deps:
            try:
                return int(model_deps['bus_recipient_id'])
            except ValueError:
                pass
        # hack: legacy code, might be dead code, if bus_recipient_id isn't set (when record is not synchronized)
        # external_key would not return any record BUT some other uses cases could be out of my mind..
        external_key = model_deps.get('external_key')
        _, sub_record = self.env['bus.binder'].get_record_by_external_key(external_key, model)
        return sub_record and sub_record.id or False

    def get_multiple_relational_value(self, model, ids, dependencies):
        result_ids = []
        for id in ids:
            result_ids.append(self.get_relational_value(model, id, dependencies))
        return result_ids
