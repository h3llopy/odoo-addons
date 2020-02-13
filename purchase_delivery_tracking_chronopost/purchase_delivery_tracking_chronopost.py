# -*- coding: utf8 -*-
#
#    Copyright (C) 2015 NDP Systèmes (<http://www.ndp-systemes.fr>).
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

from openerp import models, api, _
from urllib2 import urlopen
from lxml import etree

TRACKING_URL = 'https://www.chronopost.fr/tracking-cxf/TrackingServiceWS/trackSkybill?language=en_US&skybillNumber='


class ChronopostTrackingTransporter(models.Model):
    _inherit = 'tracking.transporter'

    @api.multi
    def _compute_logo(self):
        super(ChronopostTrackingTransporter, self)._compute_logo()
        for rec in self:
            if rec.name == 'Chronopost':
                rec.logo = "/purchase_delivery_tracking_chronopost/static/img/chronopost.png"


class ChronopostTrackingNumber(models.Model):
    _inherit = 'tracking.number'

    @api.multi
    def update_delivery_status(self):
        super(ChronopostTrackingNumber, self).update_delivery_status()
        for rec in self:
            if rec.transporter_id == self.env.ref('base_delivery_tracking_colissimo.transporter_colissimo'):
                rec.status_ids.unlink()
                file = urlopen(_(TRACKING_URL) + rec.name)
                if file:
                    list_status = etree.fromstring(file.read()).findall(".//events")
                    for c in list_status:
                        date = c.find(".//eventDate").text
                        date = date[:10] + ' ' + date[11:19]
                        self.env['tracking.status'].create({
                            'date': date,
                            'status': c.find(".//eventLabel").text,
                            'tracking_id': rec.id
                        })
