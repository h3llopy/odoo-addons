# -*- coding: utf8 -*-
#
# Copyright (C) 2018 NDP Systèmes (<http://www.ndp-systemes.fr>).
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

from openerp import models, fields, api


class ProjectProjectSync(models.Model):
    _inherit = 'project.project'

    ndp_project_sync = fields.Boolean(string=u"Synchronize with odoo NDP", default=False)


class ProjectTaskSync(models.Model):
    _inherit = 'project.task'

    ndp_sync = fields.Boolean(string=u"Need to be synchronize in odoo NDP", default=False)
    ndp_project_sync = fields.Boolean(string=u"Synchronize with odoo NDP", default=False, readonly=True, store=True,
                                      related="project_id.ndp_project_sync")

    @api.multi
    def write(self, values):
        for rec in self:
            if rec.ndp_project_sync or values.get('ndp_project_sync', False):
                values.update({'ndp_sync': True})
        return super(ProjectTaskSync, self).write(values)

    @api.model
    def create(self, values):
        if values.get('ndp_project_sync', False):
            values.update({'ndp_sync': True})
        return super(ProjectTaskSync, self).create(values)

    @api.multi
    def message_post(self, body='', subject=None, type='notification', subtype=None, parent_id=False,
                     attachments=None, **kwargs):
        res = super(ProjectTaskSync, self).message_post(body=body, subject=subject, type=type, subtype=subtype,
                                                        parent_id=parent_id, attachments=attachments, **kwargs)
        for rec in self:
            if rec.ndp_project_sync:
                rec.write({'ndp_sync': True})
        return res
