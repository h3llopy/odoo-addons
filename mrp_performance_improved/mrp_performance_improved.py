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

from openerp import models, fields


class MrpPerformanceImprovedMrpProduction(models.Model):
    _inherit = 'mrp.production'

    procurement_id = fields.Many2one('procurement.order', index=True)
    move_prod_id = fields.Many2one('stock.move', index=True)


class MrpPerformanceImprovedStockMove(models.Model):
    _inherit = 'stock.move'

    consumed_for = fields.Many2one('stock.move', index=True)


class MrpPerformanceImprovedProcurementOrder(models.Model):
    _inherit = 'procurement.order'

    production_id = fields.Many2one('mrp.production', index=True)
