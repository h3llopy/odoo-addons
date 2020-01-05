# -*- coding: utf8 -*-
#
#    Copyright (C) 2020 NDP Systèmes (<http://www.ndp-systemes.fr>).
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

from odoo import models, api, exceptions, _


class AccointInvoiceRecomputeTaxes(models.Model):
    _inherit = 'account.invoice'

    @api.multi
    def recompute_taxes_from_screen(self):
        if self.search([('id', 'in', self.ids),
                        ('state', '!=', 'draft')]):
            raise exceptions.UserError(_(u"You can only recompute VAT for draft invoices"))
        self.compute_taxes()
