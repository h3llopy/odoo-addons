# -*- coding: utf8 -*-
#
# Copyright (C) 2016 NDP Systèmes (<http://www.ndp-systemes.fr>).
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

from odoo import fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    item_ids = fields.One2many('project.task.item', 'task_id', u"Items")


class ProjectTaskItem(models.Model):
    _name = 'project.task.item'
    _order = 'sequence, id'

    task_id = fields.Many2one('project.task', u"Task")
    done = fields.Boolean(u"Done")
    description = fields.Char(u"Content", required=True)
    sequence = fields.Integer(string=u"Sequence")
