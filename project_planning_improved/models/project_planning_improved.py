# -*- coding: utf8 -*-
#
# Copyright (C) 2014 NDP Systèmes (<http://www.ndp-systemes.fr>).
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
from datetime import datetime as dt

from dateutil.relativedelta import relativedelta
from openerp import models, fields, api, _
from openerp.exceptions import UserError
from openerp.report import report_sxw

from ..models.exceptions import NotReschedulableTiaTaskError, StartDateNotWorkingPeriod, EndDateNotWorkingPeriod,\
    ReDisplayTaskForbidden

_logger = logging.getLogger(__name__)


HOUR_START_DAY = 8
HOUR_END_DAY = 17


class ProjectImprovedProject(models.Model):
    _inherit = 'project.project'

    reference_task_id = fields.Many2one('project.task', string=u"Reference task",
                                        domain=[('children_task_ids', '=', False)])
    reference_task_end_date = fields.Date(string=u"Reference task end date")
    reset_scheduling_available = fields.Boolean(string=u"Reset scheduling available", compute='_get_buttons_available')
    start_auto_planning_available = fields.Boolean(string=u"Scheduling available", compute='_get_buttons_available')

    @api.multi
    def _get_buttons_available(self):
        for rec in self:
            rec.reset_scheduling_available = rec.task_ids and any([task.taken_into_account or
                                                                   task.objective_start_date or
                                                                   task.objective_end_date or
                                                                   task.expected_start_date or
                                                                   task.expected_end_date for task in rec.task_ids])
            rec.start_auto_planning_available = rec.task_ids and not rec.start_auto_planning_available

    @api.multi
    def check_modification_reference_task_allowed(self):
        current_user = self.env.user
        for rec in self:
            if rec.user_id != current_user:
                raise UserError(_(u"You are not allowed to change the reference task (or its date) for project %s, "
                                  u"because you are not manager of this project." % rec.display_name))

    @api.multi
    def write(self, vals):
        if vals.get('reference_task_id') or vals.get('reference_task_end_date'):
            self.check_modification_reference_task_allowed()
        return super(ProjectImprovedProject, self).write(vals)

    @api.multi
    def open_task_planning(self):
        self.ensure_one()
        view = self.env.ref('project_planning_improved.project_improved_task_tree')
        ctx = self.env.context.copy()
        ctx['search_default_project_id'] = self.id
        return {
            'name': _("Tasks planning for project %s") % self.name,
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': 'project.task',
            'views': [(view.id, 'tree')],
            'view_id': view.id,
            'context': ctx,
        }

    @api.multi
    def update_critical_tasks(self):
        for rec in self:
            domain_tasks = [('project_id', '=', rec.id),
                            ('previous_task_ids', '=', False),
                            ('children_task_ids', '=', False)]
            latest_tasks = self.env['project.task'].search(domain_tasks)
            longest_ways_to_tasks = {task: {'tasks': task, 'nb_days': task.objective_duration_not_null}
                                     for task in latest_tasks}
            while latest_tasks:
                new_tasks_to_proceed = self.env['project.task']
                for latest_task in latest_tasks:
                    new_tasks_to_proceed |= self.env['project.task']. \
                        search([('id', 'child_of', latest_task.next_task_ids.ids),
                                ('children_task_ids', '=', False)])
                    for next_task in latest_task.next_task_ids:
                        set_new_way = True
                        if next_task in longest_ways_to_tasks:
                            old_duration_to_task = longest_ways_to_tasks[next_task]['nb_days']
                            new_duration_to_task = longest_ways_to_tasks[latest_task]['nb_days'] + \
                                next_task.objective_duration_not_null
                            if new_duration_to_task <= old_duration_to_task:
                                set_new_way = False
                                # Case of two critical ways
                                if new_duration_to_task == old_duration_to_task:
                                    longest_ways_to_tasks[next_task]['tasks'] |= \
                                        longest_ways_to_tasks[latest_task]['tasks']
                        if set_new_way:
                            longest_ways_to_tasks[next_task] = {
                                'tasks': longest_ways_to_tasks[latest_task]['tasks'] + next_task,
                                'nb_days': longest_ways_to_tasks[latest_task]['nb_days'] +
                                           next_task.objective_duration_not_null
                            }
                latest_tasks = new_tasks_to_proceed
            critical_nb_days = longest_ways_to_tasks and \
                               max([longest_ways_to_tasks[task]['nb_days'] for task in
                                    longest_ways_to_tasks.keys()]) or 0
            critical_tasks = self.env['project.task']
            for task in longest_ways_to_tasks.keys():
                if longest_ways_to_tasks[task]['nb_days'] == critical_nb_days:
                    critical_tasks |= longest_ways_to_tasks[task]['tasks']
            not_critical_tasks = self.env['project.task'].search([('project_id', '=', rec.id),
                                                                  ('id', 'not in', critical_tasks.ids)])
            critical_tasks.write({'critical_task': True})
            not_critical_tasks.write({'critical_task': False})

    @api.multi
    def open_tasks_timeline(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'name': _("Tasks"),
            'view_type': 'form',
            'view_mode': 'timeline,tree,form',
            'domain': [('project_id', 'in', self.ids), ('forced_duration_one_day', '=', False)],
            'context': self.env.context
        }

    @api.multi
    def start_auto_planning(self):
        for rec in self:
            rec.update_critical_tasks()
            reference_task = rec.reference_task_id
            if reference_task and rec.reference_task_end_date:
                rec.reset_dates()
                rec.update_objective_dates(reference_task)
                rec.update_objective_dates_parent_tasks()
                not_planned_tasks = self.env['project.task'].search([('project_id', '=', rec.id),
                                                                     '|', ('objective_start_date', '=', False),
                                                                     ('objective_end_date', '=', False)])
                if not_planned_tasks:
                    raise UserError(_(u"Impossible to determine objective dates for tasks %s in project %s "
                                      u"with current configuration") %
                                    (u", ".join([task.name for task in not_planned_tasks]),
                                     rec.display_name))
                rec.with_context(do_not_propagate_dates=True).configure_expected_dates()
            tasks_forced_one_day = self.env['project.task'].search([('project_id', '=', rec.id),
                                                                    ('forced_duration_one_day', '=', True)])
            tasks_forced_one_day.set_task_on_one_day()
        return self.open_tasks_timeline()

    @api.multi
    def reset_dates(self):
        tasks = self.env['project.task'].search([('project_id', 'in', self.ids),
                                                 '|', ('objective_start_date', '!=', False),
                                                 ('objective_end_date', '!=', False)])
        tasks.with_context(do_not_propagate_dates=True).write({'objective_start_date': False,
                                                               'objective_end_date': False})

    @api.multi
    def update_objective_dates(self, reference_task=False):
        for rec in self:
            reference_task = reference_task or rec.reference_task_id
            if not reference_task or not rec.reference_task_end_date:
                raise UserError(_(u"Impossible to update objective dates for project %s if reference task or its date "
                                  u"is not defined.") % rec.display_name)
            reference_task.write({
                'objective_start_date': reference_task.
                    schedule_get_date(rec.reference_task_end_date, -reference_task.objective_duration_not_null + 1),
                'objective_end_date': rec.reference_task_end_date,
            })
            previous_tasks = reference_task.previous_task_ids
            next_tasks = reference_task.next_task_ids
            planned_tasks = reference_task
            while previous_tasks or next_tasks:
                new_previous_tasks = self.env['project.task']
                new_next_tasks = self.env['project.task']
                for previous_task in previous_tasks:
                    next_tasks_with_start_dates = self.env['project.task']. \
                        search([('id', 'in', previous_task.next_task_ids.ids), ('objective_start_date', '!=', False)])
                    objective_end_date = min([task.objective_start_date for task in next_tasks_with_start_dates] or
                                             [False])
                    if objective_end_date:
                        objective_end_date = previous_task.schedule_get_date(objective_end_date, -1)
                    objective_start_date = objective_end_date and previous_task. \
                        schedule_get_date(objective_end_date, -previous_task.objective_duration_not_null + 1) or False
                    vals_previous_task = {
                        'objective_start_date': objective_start_date,
                        'objective_end_date': objective_end_date,
                    }
                    previous_task.write(vals_previous_task)
                    planned_tasks |= previous_task
                    new_previous_tasks |= previous_task.previous_task_ids. \
                        filtered(lambda task: task not in planned_tasks and
                                 not (task.critical_task and not previous_task.critical_task))
                    new_next_tasks |= previous_task.next_task_ids. \
                        filtered(lambda task: task not in planned_tasks and
                                 not (task.critical_task and not previous_task.critical_task))
                for next_task in next_tasks:
                    previous_tasks_with_end_dates = self.env['project.task']. \
                        search([('id', 'in', next_task.previous_task_ids.ids), ('objective_end_date', '!=', False)])
                    objective_start_date = max([task.objective_end_date for task in previous_tasks_with_end_dates] or
                                               [False])
                    if objective_start_date:
                        objective_start_date = next_task.schedule_get_date(objective_start_date, 1)
                    objective_end_date = objective_start_date and next_task.\
                        schedule_get_date(objective_start_date, next_task.objective_duration_not_null - 1) or False
                    vals_next_task = {
                        'objective_start_date': objective_start_date,
                        'objective_end_date': objective_end_date,
                    }
                    next_task.write(vals_next_task)
                    planned_tasks |= next_task
                    new_previous_tasks |= next_task.previous_task_ids. \
                        filtered(lambda task: task not in planned_tasks and
                                 not (task.critical_task and not next_task.critical_task))
                    new_next_tasks |= next_task.next_task_ids. \
                        filtered(lambda task: task not in planned_tasks and
                                 not (task.critical_task and not next_task.critical_task))
                previous_tasks = new_previous_tasks.filtered(lambda task: task not in planned_tasks)
                next_tasks = new_next_tasks.filtered(lambda task: task not in planned_tasks)

    @api.multi
    def update_objective_dates_parent_tasks(self):
        for rec in self:
            parent_tasks = self.env['project.task'].search([('project_id', '=', rec.id),
                                                            '|', ('objective_start_date', '=', False),
                                                            ('objective_end_date', '=', False)])
            for parent_task in parent_tasks:
                children_tasks = self.env['project.task'].search([('id', 'child_of', parent_task.id)])
                if children_tasks:
                    min_objective_start_date = min([task.objective_start_date for
                                                    task in children_tasks if task.objective_start_date] or [False])
                    max_objective_end_date = max([task.objective_end_date for
                                                  task in children_tasks if task.objective_end_date] or [False])
                    parent_task.with_context(do_not_propagate_dates=True).write({
                        'objective_start_date': min_objective_start_date,
                        'objective_end_date': max_objective_end_date,
                    })

    @api.multi
    def configure_expected_dates(self):
        for rec in self:
            parent_tasks = self.env['project.task']
            domain_not_planned_tasks = [('project_id', '=', rec.id),
                                        ('children_task_ids', '=', False),
                                        '|', ('expected_start_date', '=', False),
                                        ('expected_end_date', '=', False)]
            not_planned_tasks_with_ancestors = self.env['project.task']. \
                search(domain_not_planned_tasks + [('previous_task_ids', '!=', False)])
            for task in not_planned_tasks_with_ancestors:
                start_date = max([pt.expected_end_date for pt in task.previous_task_ids])
                parent_tasks |= task.get_all_parent_tasks()
                if start_date:
                    task.reschedule_start_date(start_date)
            not_planned_tasks_with_successors = self.env['project.task']. \
                search(domain_not_planned_tasks + [('next_task_ids', '!=', False)])
            for task in not_planned_tasks_with_successors:
                end_date = min([pt.expected_start_date for pt in task.next_task_ids])
                parent_tasks |= task.get_all_parent_tasks()
                if end_date:
                    task.reschedule_end_date(end_date)
            still_not_planned_tasks = self.env['project.task'].search(domain_not_planned_tasks)
            for task in still_not_planned_tasks:
                parent_tasks |= task.get_all_parent_tasks()
                task.with_context(do_not_propagate_dates=True, force_update_tia=True).write({
                    'expected_start_date': task.objective_start_date,
                    'expected_end_date': task.objective_end_date,
                })
            for parent_task in parent_tasks:
                children_tasks = self.env['project.task'].search([('id', 'child_of', parent_task.id),
                                                                  ('children_task_ids', '=', False),
                                                                  ('id', '!=', parent_task.id)])
                start_date = min([task.expected_start_date for task in children_tasks])
                end_date = max([task.expected_end_date for task in children_tasks])
                if end_date and parent_task.expected_end_date != end_date:
                    parent_task.with_context(do_not_propagate_dates=True).write({
                        'expected_start_date': start_date,
                        'expected_end_date': end_date,
                    })
            rec.reference_task_id.taken_into_account = True

    @api.multi
    def set_tasks_not_tia(self):
        vals = self.env.context.get('tasks_new_vals', {})
        vals['taken_into_account'] = False
        tasks = self.env['project.task'].search([('project_id', 'in', self.ids)])
        tasks.write(vals)
        return tasks

    @api.multi
    def reset_scheduling(self):
        self.with_context(tasks_new_vals={'objective_start_date': False,
                                          'objective_end_date': False,
                                          'expected_start_date': False,
                                          'expected_end_date': False}).set_tasks_not_tia()

    @api.multi
    def update_dates_parent_tasks(self, avoid_task_ids=None):
        for rec in self:
            parent_tasks = self.env['project.task']
            domain_parent_tasks  = [('project_id', '=', rec.id),
                                    ('parent_task_id', '!=', False)]
            if avoid_task_ids:
                domain_parent_tasks += [('parent_task_id', 'not in', avoid_task_ids)]
            for task in self.env['project.task'].search(domain_parent_tasks):
                parent_tasks |= task.parent_task_id
            if not parent_tasks:
                return
            children_tasks = self.env['project.task'].search([('project_id', '=', rec.id),
                                                              ('id', 'not in', parent_tasks.ids)])
            if not children_tasks:
                return
            self.env.cr.execute("""WITH RECURSIVE top_parent(task_id, top_parent_task_id) AS (
  SELECT pt.id AS task_id,
         pt.id AS top_parent_task_id
  FROM project_task pt
         LEFT JOIN project_task ptp ON ptp.id = pt.parent_task_id
  WHERE pt.project_id = %s
  UNION
  SELECT pt.id AS task_id,
         tp.top_parent_task_id
  FROM project_task pt,
       top_parent tp
  WHERE pt.parent_task_id = tp.task_id
)

SELECT parent_task.id                      AS parent_task_id,
       min(child_task.expected_start_date) AS new_expected_start_date,
       max(child_task.expected_end_date)   AS new_expected_end_date
FROM project_task parent_task
       INNER JOIN top_parent tp ON tp.top_parent_task_id = parent_task.id AND tp.task_id != parent_task.id
       LEFT JOIN project_task child_task ON child_task.id = tp.task_id AND
                                            child_task.expected_start_date IS NOT NULL AND
                                            child_task.expected_end_date IS NOT NULL AND
                                            child_task.id IN %s AND
                                            COALESCE(child_task.forced_duration_one_day, FALSE) IS FALSE
WHERE top_parent_task_id IN %s AND COALESCE(parent_task.forced_duration_one_day, FALSE) IS FALSE
GROUP BY parent_task.id""", (rec.id, tuple(children_tasks.ids), tuple(parent_tasks.ids)))
            for parent_task_id, new_expected_start_date, new_expected_end_date in self.env.cr.fetchall():
                parent_task = self.env['project.task'].browse(parent_task_id)
                parent_task.update_expected_dates_no_write(new_expected_start_date, new_expected_end_date)
        self.env.invalidate_all()


class ProjectImprovedTask(models.Model):
    _inherit = 'project.task'
    _parent_name = 'parent_task_id'

    parent_task_id = fields.Many2one('project.task', string=u"Parent task", index=True)
    previous_task_ids = fields.Many2many('project.task', 'project_task_order_rel', 'next_task_id',
                                         'previous_task_id', string=u"Previous tasks")
    next_task_ids = fields.Many2many('project.task', 'project_task_order_rel', 'previous_task_id',
                                     'next_task_id', string=u"Next tasks")
    children_task_ids = fields.One2many('project.task', 'parent_task_id', string=u"Children tasks")
    objective_duration = fields.Integer(string=u"Objective Needed Time (in days)")
    objective_duration_not_null = fields.Integer(string=u"Objective Needed Time (in days, not null)",
                                                 compute='_compute_objective_duration_not_null')
    critical_task = fields.Boolean(string=u"Critical task", readonly=True)
    objective_end_date = fields.Date(string=u"Objective end date", readonly=True)
    objective_start_date = fields.Date(string=u"Objective start date", readonly=True)
    expected_start_date = fields.Date(string=u"Expected start date", index=True)
    expected_end_date = fields.Date(string=u"Expected end date", index=True)
    expected_start_date_display = fields.Datetime(string=u"Expected start date (display)", readonly=True,
                                                  compute='_compute_expected_start_date_display', store=True)
    expected_end_date_display = fields.Datetime(string=u"Expected end date (display)", readonly=True,
                                                compute='_compute_expected_end_date_display', store=True)
    expected_duration = fields.Float(string=u"Expected duration (days)", readonly=True)
    allocated_duration = fields.Float(string=u"Allocated duration (days)")
    allocated_duration_unit_tasks = fields.Float(string=u"Allocated duration for unit tasks",
                                                 help=u"In project time unit of the comany",
                                                 compute='_get_allocated_duration')
    total_allocated_duration = fields.Integer(string=u"Total allocated duration", compute='_get_allocated_duration',
                                              help=u"In project time unit of the comany")
    taken_into_account = fields.Boolean(string=u"Taken into account")
    conflict = fields.Boolean(string=u"Conflict")
    ready_for_execution = fields.Boolean(string=u"Ready for execution", readonly=True, track_visibility=True)
    notify_users_when_dates_change = fields.Boolean(string=u"Notify users when dates change",
                                                    help=u"An additional list of users is defined in project "
                                                         u"configuration")
    forced_duration_one_day = fields.Boolean(string=u"Duration forced at one day", readonly=True)
    hidden_from_task_id = fields.Many2one('project.task', string=u"Hidden from task", readonly=True)
    nb_days_after_for_start = fields.Integer(string=u"Number of days after 'hidden from task' for start date")
    nb_days_after_for_end = fields.Integer(string=u"Number of days after 'hidden from task' for end date")

    @api.constrains('expected_start_date', 'expected_end_date')
    def constraint_dates_consistency(self):
        for rec in self:
            if rec.expected_start_date and not rec.is_working_day(fields.Date.from_string(rec.expected_start_date)):
                raise StartDateNotWorkingPeriod(rec, rec.expected_start_date)
            if rec.expected_end_date and not rec.is_working_day(fields.Date.from_string(rec.expected_end_date)):
                raise EndDateNotWorkingPeriod(rec, rec.expected_end_date)

    @api.depends('expected_start_date')
    def _compute_expected_start_date_display(self):
        for rec in self:
            expected_start_date_display = False
            if rec.expected_start_date:
                expected_start_date_display = rec.expected_start_date + (' %s:00:00' % ('%02d' % HOUR_START_DAY))
            rec.expected_start_date_display = expected_start_date_display

    @api.depends('expected_end_date')
    def _compute_expected_end_date_display(self):
        for rec in self:
            expected_end_date_display = False
            if rec.expected_end_date:
                expected_end_date_display = rec.expected_end_date + (' %s:00:00' % ('%02d' % HOUR_END_DAY))
            rec.expected_end_date_display = expected_end_date_display

    @api.depends('children_task_ids', 'children_task_ids.total_allocated_duration', 'allocated_duration')
    @api.multi
    def _get_allocated_duration(self):
        records = self
        while records:
            rec = records[0]
            if any([task in records for task in rec.children_task_ids]):
                records = records[1:]
                records += rec
            else:
                rec.allocated_duration_unit_tasks = sum(line.total_allocated_duration for
                                                        line in rec.children_task_ids)
                rec.total_allocated_duration = rec.allocated_duration + rec.allocated_duration_unit_tasks
                records -= rec

    @api.multi
    def _compute_objective_duration_not_null(self):
        for rec in self:
            rec.objective_duration_not_null = rec.objective_duration or 1

    @api.onchange('expected_start_date', 'expected_end_date')
    @api.multi
    def onchange_expected_dates(self):
        for rec in self:
            rec.taken_into_account = True

    @api.multi
    def get_default_calendar_and_resource(self):
        use_calendar = not self.env.context.get('do_not_use_any_calendar')
        resource = False
        reference_user = self.user_id or self.env.user
        if reference_user:
            resource = self.env['resource.resource'].search([('user_id', '=', reference_user.id),
                                                             ('resource_type', '=', 'user')], limit=1)
        if not resource:
            resource = self.env['resource.resource'].search([('user_id', '=', self.env.user.id),
                                                             ('resource_type', '=', 'user')], limit=1)
        calendar = False
        if use_calendar:
            calendar = resource and resource.calendar_id or self.company_id.calendar_id or \
                self.env.ref('resource_improved.default_calendar')
        return resource, calendar

    @api.multi
    def schedule_get_date(self, date_ref, nb_days=0):
        """
        From a task (self), this function computes the date which is 'nb_days' days after day 'date_ref'.
        :param date_ref: fields.Date
        :param nb_days: Number of days to add/remove:
        :return fields.Date
        """
        self.ensure_one()
        target_date = fields.Date.from_string(date_ref)
        if nb_days:
            step = relativedelta(days=nb_days > 0 and 1 or -1)
            target_nb_working_days = abs(int(nb_days))
            nb_working_days = 0
            while nb_working_days < target_nb_working_days:
                target_date += step
                if self.is_working_day(target_date):
                    nb_working_days += 1
        return fields.Date.to_string(target_date)

    @api.multi
    def get_all_parent_tasks(self, only_not_tia=False):
        self.ensure_one()
        parent_tasks = self.parent_task_id
        parent = self.parent_task_id
        while parent.parent_task_id:
            parent = parent.parent_task_id
            parent_tasks |= parent.parent_task_id
        if only_not_tia:
            return self.env['project.task'].search([('id', 'in', parent_tasks.ids),
                                                    ('taken_into_account', '=', False)])
        return parent_tasks

    @api.multi
    def check_not_tia(self):
        for rec in self:
            if rec.taken_into_account:
                raise NotReschedulableTiaTaskError(rec)

    @api.multi
    def is_automanaged_view(self):
        # TODO: timeline est passé même en vue formulaire
        return self.env.context.get('params', {}).get('view_type') == 'timeline'

    @api.multi
    def get_vals_for_task(self, vals, propagating_tasks, slide_tasks):
        self.ensure_one()
        vals_copy = vals.copy()
        if slide_tasks[self] and not propagating_tasks:
            vals_copy['expected_end_date'] = self.schedule_get_date(vals_copy['expected_start_date'],
                                                                    self.get_task_number_open_days() - 1)
        start_date_changed = vals.get('expected_start_date') and \
                             vals_copy['expected_start_date'] != self.expected_start_date and True or False
        end_date_changed = vals.get('expected_end_date') and \
                           vals_copy['expected_end_date'] != self.expected_end_date and True or False
        if start_date_changed or end_date_changed:
            msg = u"Task %s rescheduled: "
            args = [self.name]
            if start_date_changed:
                msg += u"start date %s"
                args += [vals_copy.get('expected_start_date', self.expected_start_date)]
            if end_date_changed:
                msg += ((start_date_changed and u", " or u"") + u"end date %s")
                args += [vals_copy.get('expected_end_date', self.expected_end_date)]
            msg = msg % tuple(args)
            _logger.info(msg)
        if vals_copy.get('expected_start_date'):
            vals_copy['expected_start_date_display'] = vals_copy.get('expected_start_date') + ' 08:00:00'
        if vals_copy.get('expected_end_date'):
            vals_copy['expected_end_date_display'] = vals_copy.get('expected_end_date') + ' 18:00:00'
        if start_date_changed or end_date_changed:
            start_date = vals_copy.get('expected_start_date', self.expected_start_date)
            end_date = vals_copy.get('expected_end_date', self.expected_end_date)
            vals_copy['expected_duration'] = self.get_task_number_open_days(start_date, end_date)
        return vals_copy, start_date_changed, end_date_changed

    @api.multi
    def propagate_to_the_past_or_to_the_future(self, vals, start_date_changed, end_date_changed):
        self.ensure_one()
        propagate_to_the_future = self.env.context.get('propagate_to_the_future', False)
        propagate_to_the_past = self.env.context.get('propagate_to_the_past', False)
        if not self.env.context.get('propagating_tasks'):
            if start_date_changed and vals['expected_start_date'] < self.expected_start_date or \
                    end_date_changed and vals['expected_end_date'] < self.expected_end_date:
                propagate_to_the_past = True
            if start_date_changed and vals['expected_start_date'] > self.expected_start_date or \
                    end_date_changed and vals['expected_end_date'] > self.expected_end_date:
                propagate_to_the_future = True
        return propagate_to_the_future, propagate_to_the_past

    @api.multi
    def get_next_tasks_of_task_and_parents(self):
        self.ensure_one()
        task = self
        next_tasks = self.env['project.task'].search([('id', 'child_of', task.next_task_ids.ids)])
        while task.parent_task_id:
            task = task.parent_task_id
            next_tasks |= self.env['project.task'].search([('id', 'child_of', task.next_task_ids.ids)])
        return next_tasks

    @api.multi
    def get_previous_tasks_of_task_and_parents(self):
        self.ensure_one()
        task = self
        previous_tasks = self.env['project.task'].search([('id', 'child_of', task.previous_task_ids.ids)])
        while task.parent_task_id:
            task = task.parent_task_id
            previous_tasks |= self.env['project.task'].search([('id', 'child_of', task.previous_task_ids.ids)])
        return previous_tasks

    @api.multi
    def get_tasks_to_postpone(self):
        self.ensure_one()
        do_not_reschedule_task_ids = self.env.context.get('do_not_reschedule_task_ids', [])
        tasks_to_postpone_entirely = self.env['project.task']
        next_tasks_of_task_and_parents = self.get_next_tasks_of_task_and_parents()
        first_task_to_postpone = self.env['project.task']. \
            search([('id', 'in', next_tasks_of_task_and_parents.ids),
                    ('id', 'not in', do_not_reschedule_task_ids),
                    ('expected_start_date', '<=', self.expected_end_date)], order='expected_start_date', limit=1)
        first_start_date_to_postpone = first_task_to_postpone and first_task_to_postpone.expected_start_date or False
        nb_days = first_task_to_postpone and first_task_to_postpone. \
            get_task_number_open_days(first_task_to_postpone.expected_start_date, self.expected_end_date) or 0
        if nb_days != 0:
            tasks_to_postpone_entirely = self.env['project.task']. \
                search([('project_id', '=', self.project_id.id),
                        ('id', '!=', self.id),
                        ('id', 'not in', do_not_reschedule_task_ids),
                        ('expected_start_date', '>=', first_start_date_to_postpone)])
        return tasks_to_postpone_entirely, first_start_date_to_postpone, nb_days

    @api.multi
    def get_children_tasks_to_postpone(self):
        self.ensure_one()
        do_not_reschedule_task_ids = self.env.context.get('do_not_reschedule_task_ids', [])
        tasks_to_postpone_entirely = self.env['project.task']
        first_task_to_postpone = self.env['project.task']. \
            search([('id', 'child_of', self.children_task_ids.ids),
                    ('id', 'not in', do_not_reschedule_task_ids),
                    ('expected_start_date', '<', self.expected_start_date)], order='expected_start_date', limit=1)
        first_start_date_to_postpone = first_task_to_postpone and first_task_to_postpone.expected_start_date or False
        nb_days = first_task_to_postpone and first_task_to_postpone. \
            get_task_number_open_days(first_start_date_to_postpone, self.expected_start_date) or 0
        nb_days = max(nb_days - 1, 0)
        if nb_days != 0:
            tasks_to_postpone_entirely = self.env['project.task']. \
                search([('project_id', '=', self.project_id.id),
                        ('id', '!=', self.id),
                        ('id', 'not in', do_not_reschedule_task_ids),
                        ('expected_start_date', '>=', first_start_date_to_postpone)])
        return tasks_to_postpone_entirely, first_start_date_to_postpone, nb_days

    @api.multi
    def get_tasks_to_advance(self):
        self.ensure_one()
        do_not_reschedule_task_ids = self.env.context.get('do_not_reschedule_task_ids', [])
        tasks_to_advance_entirely = self.env['project.task']
        previous_tasks_of_task_and_parents = self.get_previous_tasks_of_task_and_parents()
        last_task_to_advance = self.env['project.task']. \
            search([('id', 'in', previous_tasks_of_task_and_parents.ids),
                    ('id', 'not in', do_not_reschedule_task_ids),
                    ('expected_end_date', '>=', self.expected_start_date)], order='expected_end_date desc', limit=1)
        last_end_date_to_advance = last_task_to_advance and last_task_to_advance.expected_end_date or False
        nb_days = last_task_to_advance and last_task_to_advance. \
            get_task_number_open_days(self.expected_start_date, last_task_to_advance.expected_end_date) or 0
        if nb_days != 0:
            tasks_to_advance_entirely = self.env['project.task']. \
                search([('project_id', '=', self.project_id.id),
                        ('id', '!=', self.id),
                        ('id', 'not in', do_not_reschedule_task_ids),
                        ('expected_end_date', '<=', last_end_date_to_advance)])
        return tasks_to_advance_entirely, last_end_date_to_advance, nb_days

    @api.multi
    def get_children_tasks_to_advance(self):
        self.ensure_one()
        do_not_reschedule_task_ids = self.env.context.get('do_not_reschedule_task_ids', [])
        tasks_to_advance_entirely = self.env['project.task']
        last_task_to_advance = self.env['project.task']. \
            search([('id', 'child_of', self.children_task_ids.ids),
                    ('id', 'not in', do_not_reschedule_task_ids),
                    ('expected_end_date', '>', self.expected_end_date)], order='expected_end_date desc', limit=1)
        last_end_date_to_advance = last_task_to_advance and last_task_to_advance.expected_end_date or False
        nb_days = last_task_to_advance and last_task_to_advance. \
            get_task_number_open_days(self.expected_end_date, last_end_date_to_advance) or 0
        nb_days = max(nb_days - 1, 0)
        if nb_days != 0:
            tasks_to_advance_entirely = self.env['project.task']. \
                search([('project_id', '=', self.project_id.id),
                        ('id', '!=', self.id),
                        ('id', 'not in', do_not_reschedule_task_ids),
                        ('expected_end_date', '<=', last_end_date_to_advance)])
        return tasks_to_advance_entirely, last_end_date_to_advance, nb_days

    @api.multi
    def get_usefull_working_days_to_postpone(self, start_date, end_date, nb_days_to_add):
        date = fields.Date.from_string(start_date)
        last_end_date_to_postpone = fields.Date.from_string(end_date)
        usefull_working_days = []
        usefull_non_working_days = []
        last_end_day_is_working = True
        while date <= last_end_date_to_postpone or not last_end_day_is_working:
            if self.is_working_day(date):
                usefull_working_days += [fields.Date.to_string(date)]
                last_end_day_is_working = True
            else:
                usefull_non_working_days += [fields.Date.to_string(date)]
                last_end_day_is_working = False
            date += relativedelta(days=1)
        nb_usefull_dates_to_add = nb_days_to_add
        while nb_usefull_dates_to_add or not last_end_day_is_working:
            if self.is_working_day(date):
                nb_usefull_dates_to_add -= 1
                usefull_working_days += [fields.Date.to_string(date)]
                last_end_day_is_working = True
            else:
                usefull_non_working_days += [fields.Date.to_string(date)]
                last_end_day_is_working = False
            date += relativedelta(days=1)
        return usefull_working_days, usefull_non_working_days

    @api.multi
    def get_usefull_working_days_to_advance(self, end_date, start_date, nb_days_to_add):
        date = fields.Date.from_string(end_date)
        first_start_date_to_advance = fields.Date.from_string(start_date)
        usefull_working_days = []
        usefull_non_working_days = []
        last_end_day_is_working = True
        while date >= first_start_date_to_advance or not last_end_day_is_working:
            if self.is_working_day(date):
                usefull_working_days += [fields.Date.to_string(date)]
                last_end_day_is_working = True
            else:
                usefull_non_working_days += [fields.Date.to_string(date)]
                last_end_day_is_working = False
            date -= relativedelta(days=1)
        nb_usefull_dates_to_add = nb_days_to_add
        while nb_usefull_dates_to_add or not last_end_day_is_working:
            if self.is_working_day(date):
                nb_usefull_dates_to_add -= 1
                usefull_working_days += [fields.Date.to_string(date)]
                last_end_day_is_working = True
            else:
                usefull_non_working_days += [fields.Date.to_string(date)]
                last_end_day_is_working = False
            date -= relativedelta(days=1)
        return usefull_working_days, usefull_non_working_days

    @api.multi
    def update_expected_dates_no_write(self, expected_start_date, expected_end_date):
        self.ensure_one()
        if self.expected_start_date == expected_start_date and self.expected_end_date == expected_end_date:
            return
        if expected_start_date > expected_end_date:
            raise UserError(_(u"Task %s: impossible to set start date after end date") % self.display_name)
        self.check_not_tia()
        query = """WITH data AS (
  SELECT %s::DATE AS new_start_date,
         %s::DATE AS new_end_date,
         %s       AS current_user_id)

UPDATE project_task
SET expected_start_date         = (SELECT new_start_date FROM data),
    expected_start_date_display = ((SELECT new_start_date FROM data) + INTERVAL '%s hours')::TIMESTAMP,
    expected_end_date=(SELECT new_end_date FROM data),
    expected_end_date_display=((SELECT new_end_date FROM data) + INTERVAL '%s hours')::TIMESTAMP,
    write_uid                   = (SELECT current_user_id FROM data),
    write_date                  = CURRENT_TIMESTAMP
WHERE id = %s"""
        params = (expected_start_date, expected_end_date, self.env.user.id, HOUR_START_DAY, HOUR_END_DAY, self.id)
        self.env.cr.execute(query, params)
        self.env.invalidate_all()

    @api.multi
    def postpone_tasks_of_nb_days(self, tasks_to_postpone, first_date_to_postpone, nb_days):
        self.ensure_one()
        if not tasks_to_postpone:
            return
        last_task = self.search([('id', 'in', tasks_to_postpone.ids),
                                 ('expected_end_date', '!=', False)], order='expected_end_date desc', limit=1)
        if not last_task:
            return
        usefull_working_days, usefull_non_working_days = self. \
            get_usefull_working_days_to_postpone(first_date_to_postpone, last_task.expected_end_date, nb_days)
        nb_usefull_working_days = len(usefull_working_days)
        index = 0
        dict_date_modification = {}
        while index < nb_usefull_working_days - nb_days:
            dict_date_modification[usefull_working_days[index]] = usefull_working_days[index + nb_days]
            index += 1
        # We schedule replanification of a non-working date to next working day
        max_date_in_dict = max(dict_date_modification.keys())
        for non_working_date in usefull_non_working_days:
            date = non_working_date
            while non_working_date not in dict_date_modification:
                date_dt = fields.Date.from_string(date) + relativedelta(days=1)
                date = fields.Date.to_string(date_dt)
                if date in dict_date_modification:
                    dict_date_modification[non_working_date] = date
                    continue
                if date > max_date_in_dict and self.is_working_day(date_dt):
                    dict_date_modification[non_working_date] = date
        for task in tasks_to_postpone:
            task.update_expected_dates_no_write(dict_date_modification[task.expected_start_date],
                                                dict_date_modification[task.expected_end_date])

    @api.multi
    def advance_tasks_of_nb_days(self, tasks_to_advance, last_date_to_advance, nb_days):
        self.ensure_one()
        if not tasks_to_advance:
            return
        first_task = self.search([('id', 'in', tasks_to_advance.ids),
                                 ('expected_start_date', '!=', False)], order='expected_start_date', limit=1)
        if not first_task:
            return
        usefull_working_days, usefull_non_working_days = self. \
            get_usefull_working_days_to_advance(last_date_to_advance, first_task.expected_start_date, nb_days)
        nb_usefull_working_days = len(usefull_working_days)
        index = 0
        dict_date_modification = {}
        while index < nb_usefull_working_days - nb_days:
            dict_date_modification[usefull_working_days[index]] = usefull_working_days[index + nb_days]
            index += 1
        # We schedule replanification of a non-working date to next working day
        min_date_in_dict = min(dict_date_modification.keys())
        for non_working_date in usefull_non_working_days:
            date = non_working_date
            while non_working_date not in dict_date_modification:
                date_dt = fields.Date.from_string(date) - relativedelta(days=1)
                date = fields.Date.to_string(date_dt)
                if date in dict_date_modification:
                    dict_date_modification[non_working_date] = date
                    continue
                if date < min_date_in_dict and self.is_working_day(date_dt):
                    dict_date_modification[non_working_date] = date
        for task in tasks_to_advance:
            task.update_expected_dates_no_write(dict_date_modification[task.expected_start_date],
                                                dict_date_modification[task.expected_end_date])

    @api.multi
    def write(self, vals):
        if not self:
            return True
        if 'objective_start_date' in vals or 'objective_end_date' in vals:
            for rec in self:
                _logger.info(u"Scheduling task %s for objective_start_date %s and objective end date %s",
                             rec.name,
                             vals.get('objective_start_date', rec.objective_start_date),
                             vals.get('objective_end_date', rec.objective_end_date))
        expected_start_date_display = vals.get('expected_start_date_display')
        if expected_start_date_display:
            expected_start_date_display_dt = fields.Date.from_string(expected_start_date_display[:10])
            while not self[0].is_working_day(expected_start_date_display_dt):
                expected_start_date_display_dt += relativedelta(days=1)
            vals.pop('expected_start_date_display')
            vals['expected_start_date'] = fields.Date.to_string(expected_start_date_display_dt)
        expected_end_date_display = vals.get('expected_end_date_display')
        if expected_end_date_display:
            expected_end_date_display_dt = fields.Date.from_string(expected_end_date_display[:10])
            while not self[0].is_working_day(expected_end_date_display_dt):
                expected_end_date_display_dt -= relativedelta(days=1)
            vals.pop('expected_end_date_display')
            vals['expected_end_date'] = fields.Date.to_string(expected_end_date_display_dt)
        propagate_dates = not self.env.context.get('do_not_propagate_dates')
        propagating_tasks = self.env.context.get('propagating_tasks')
        slide_tasks = self.get_slide_tasks(vals)
        for rec in self:
            vals_copy, start_date_changed, end_date_changed = rec. \
                get_vals_for_task(vals, propagating_tasks, slide_tasks)
            dates_changed = start_date_changed or end_date_changed or self.env.context.get('force_dates_changed')
            if dates_changed and 'taken_into_account' not in vals and not self.env.context.get('force_update_tia'):
                self.check_not_tia()
            propagate_to_the_future, propagate_to_the_past = rec. \
                propagate_to_the_past_or_to_the_future(vals_copy, start_date_changed, end_date_changed)
            expected_start_date = vals_copy.get('expected_start_date', rec.expected_start_date)
            expected_end_date = vals_copy.get('expected_end_date', rec.expected_end_date)
            if expected_start_date and expected_end_date and expected_start_date > expected_end_date:
                raise UserError(_(u"Task %s: impossible to set start date after end date") % rec.display_name)
            super(ProjectImprovedTask, rec).write(vals_copy)
            self.env.invalidate_all()
            do_not_rechedule_parent_task_ids = self.env.context.get('do_not_rechedule_parent_task_ids', [])
            do_not_rechedule_parent_task_ids += [rec.id]
            if rec.expected_start_date and rec.expected_end_date and propagate_dates and dates_changed:
                if propagate_to_the_future:
                    tasks_to_postpone, first_start_date_to_postpone, nb_days = rec.get_children_tasks_to_postpone()
                    if tasks_to_postpone:
                        rec.postpone_tasks_of_nb_days(tasks_to_postpone, first_start_date_to_postpone, nb_days)
                    rec.project_id.update_dates_parent_tasks(avoid_task_ids=do_not_rechedule_parent_task_ids)
                    tasks_to_postpone, first_start_date_to_postpone, nb_days = rec.get_tasks_to_postpone()
                    if tasks_to_postpone:
                        rec.postpone_tasks_of_nb_days(tasks_to_postpone, first_start_date_to_postpone, nb_days)
                    rec.project_id.update_dates_parent_tasks(avoid_task_ids=do_not_rechedule_parent_task_ids)
                if propagate_to_the_past:
                    tasks_to_advance, last_end_date_to_advance, nb_days = rec.get_children_tasks_to_advance()
                    if tasks_to_advance:
                        rec.advance_tasks_of_nb_days(tasks_to_advance, last_end_date_to_advance, nb_days)
                    rec.project_id.update_dates_parent_tasks(avoid_task_ids=do_not_rechedule_parent_task_ids)
                    tasks_to_advance, last_end_date_to_advance, nb_days = rec.get_tasks_to_advance()
                    if tasks_to_advance:
                        rec.advance_tasks_of_nb_days(tasks_to_advance, last_end_date_to_advance, nb_days)
                    rec.project_id.update_dates_parent_tasks(avoid_task_ids=do_not_rechedule_parent_task_ids)
            if dates_changed:
                rec.project_id.update_dates_parent_tasks(avoid_task_ids=do_not_rechedule_parent_task_ids)
        self.notify_users_if_needed(vals)
        return True

    @api.multi
    def notify_users_if_needed(self, vals):
        dates_changed = (vals.get('expected_start_date') or vals.get('expected_end_date')) and True or False
        for rec in self:
            if dates_changed and rec.notify_users_when_dates_change:
                rec.notify_users_for_date_change()

    @api.multi
    def get_partner_to_notify_ids(self):
        self.ensure_one()
        partners_to_notify_config = self.env['ir.config_parameter']. \
            get_param('project_planning_improved.notify_date_changes_for_partner_ids', '[]')
        return eval(partners_to_notify_config) or []

    @api.multi
    def get_notification_subject(self):
        self.ensure_one()
        return _(u"Replanification of task %s in project %s") % (self.display_name, self.project_id.display_name)

    @api.multi
    def get_notification_body(self):
        self.ensure_one()
        rml_obj = report_sxw.rml_parse(self.env.cr, self.env.uid, 'project.task', dict(self.env.context))
        rml_obj.localcontext.update({'lang': self.env.context.get('lang', False)})
        return _(u"%s has changed the dates of task %s in project %s: expected start date %s, expected end date %s.") % \
            (self.env.user.partner_id.name, self.display_name, self.project_id.display_name,
             rml_obj.formatLang(self.expected_start_date, date=True),
             rml_obj.formatLang(self.expected_end_date, date=True))

    @api.multi
    def notify_users_for_date_change(self):
        self.ensure_one()
        email_from = self.env['mail.message']._get_default_from()
        partner_to_notify_ids = self.get_partner_to_notify_ids()
        for rec in self:
            for partner_id in partner_to_notify_ids:
                if partner_id == self.env.user.partner_id.id:
                    continue
                partner = self.env['res.partner'].browse(partner_id)
                channels = self.env['mail.channel']. \
                    search([('channel_partner_ids', '=', partner_id),
                            ('channel_partner_ids', '=', self.env.user.partner_id.id),
                            ('email_send', '=', False),
                            ('group_ids', '=', False)])
                chosen_channel = self.env['mail.channel']
                for channel in channels:
                    if len(channel.channel_partner_ids) == 2:
                        chosen_channel = channel
                        break
                if not chosen_channel:
                    chosen_channel = self.env['mail.channel'].create({
                        'name': "%s, %s" % (partner.name, self.env.user.partner_id.name),
                        'public': 'private',
                        'email_send': False,
                        'channel_partner_ids': [(6, 0, [partner_id, self.env.user.partner_id.id])]
                    })
                message = self.env['mail.message'].create({
                    'subject': rec.get_notification_subject(),
                    'body': rec.get_notification_body(),
                    'record_name': rec.name,
                    'email_from': email_from,
                    'reply_to': email_from,
                    'model': 'project.task',
                    'res_id': rec.id,
                    'no_auto_thread': True,
                    'channel_ids': [(6, 0, chosen_channel.ids)],
                })
                partner.with_context(auto_delete=True)._notify(message, force_send=True, user_signature=True)

    @api.multi
    def get_slide_tasks(self, vals):
        slide_tasks = {rec: False for rec in self}
        if self.is_automanaged_view() and 'expected_start_date' in vals and 'expected_end_date' in vals:
            for rec in self:
                if not rec.expected_start_date or not rec.expected_end_date:
                    continue
                old_start_date_dt = fields.Datetime.from_string(rec.expected_start_date)
                old_end_date_dt = fields.Datetime.from_string(rec.expected_end_date)
                new_start_date_dt = fields.Datetime.from_string(vals['expected_start_date'])
                new_end_date_dt = fields.Datetime.from_string(vals['expected_end_date'])
                slide_tasks[rec] = old_end_date_dt - old_start_date_dt == new_end_date_dt - new_start_date_dt
        return slide_tasks

    @api.multi
    def is_working_day(self, date):
        self.ensure_one()
        resource, calendar = self[0].get_default_calendar_and_resource()
        list_intervals = False
        if calendar:
            list_intervals = calendar.get_working_intervals_of_day(start_dt=dt(date.year, date.month, date.day),
                                                                   compute_leaves=True,
                                                                   resource_id=resource and resource.id or False)
        return list_intervals and list_intervals[0] and True or False

    @api.multi
    def get_task_number_open_days(self, start_date=None, end_date=None):
        self.ensure_one()
        open_days = 0
        start = fields.Date.from_string(start_date or self.expected_start_date)
        end = fields.Date.from_string(end_date or self.expected_end_date)
        while start <= end:
            if self.is_working_day(start):
                open_days += 1
            start += relativedelta(days=1)
        return open_days

    @api.multi
    def get_occupation_task_rate(self):
        self.ensure_one()
        task_rate = 0
        open_days = self.get_task_number_open_days()
        if open_days > 0:
            task_rate = self.allocated_duration / open_days
        return task_rate

    @api.multi
    def get_all_working_days_for_tasks(self):
        list_working_days = []
        if self:
            min_date = min([task.expected_start_date for task in self if task.expected_start_date])
            max_date = max([task.expected_end_date for task in self if task.expected_end_date])
            if min_date and max_date:
                ref_date = fields.Date.from_string(min_date)
                max_date = fields.Date.from_string(max_date)
                while ref_date <= max_date:
                    if self[0].is_working_day(ref_date):
                        list_working_days += [ref_date]
                    ref_date += relativedelta(days=1)
        return list_working_days

    @api.multi
    def update_ready_for_execution(self):
        for rec in self:
            rec.ready_for_execution = all([task.kanban_state == 'ready' for task in rec.previous_task_ids])

    @api.model
    def cron_update_ready_for_execution(self):
        self.search([('project_id.state', 'not in', ['cancelled', 'close'])]). \
            with_context(do_not_propagate_dates=True).update_ready_for_execution()

    @api.multi
    def advance_next_task_to_past_to_follow_replanification(self, initial_end_date, new_start_date,
                                                            only_same_parent_task_if_any=False):
        self.ensure_one()
        parent_task_initial_end_date = self.parent_task_id and self.parent_task_id.expected_end_date or False
        next_tasks_of_task_and_parents = self.get_next_tasks_of_task_and_parents()
        domain = [('id', 'in', next_tasks_of_task_and_parents.ids),
                  ('expected_start_date', '!=', False),
                  ('expected_start_date', '>', initial_end_date),
                  ('children_task_ids', '=', False)]
        if self.parent_task_id and only_same_parent_task_if_any:
            domain += [('id', 'child_of', self.parent_task_id.children_task_ids.ids)]
        first_task_to_advance = self.env['project.task'].search(domain, order='expected_start_date', limit=1)
        if first_task_to_advance:
            first_start_date_to_advance = first_task_to_advance.expected_start_date
            nb_days = first_task_to_advance. \
                          get_task_number_open_days(new_start_date, first_task_to_advance.expected_start_date) or 0
            nb_days = max(nb_days - 1, 0)
            if nb_days:
                domain = [('project_id', '=', self.project_id.id),
                          ('id', '!=', self.id),
                          ('expected_start_date', '>=', first_start_date_to_advance),
                          ('children_task_ids', '=', False)]
                if self.parent_task_id and only_same_parent_task_if_any:
                    domain += [('id', 'child_of', self.parent_task_id.children_task_ids.ids)]
                tasks_to_advance = self.env['project.task'].search(domain, order='expected_end_date desc')
                if tasks_to_advance:
                    last_date_to_advance = tasks_to_advance[0].expected_end_date
                    self.advance_tasks_of_nb_days(tasks_to_advance, last_date_to_advance, nb_days)
        self.project_id.update_dates_parent_tasks()
        if parent_task_initial_end_date and self.parent_task_id.expected_end_date < parent_task_initial_end_date:
            new_start_date = self.schedule_get_date(self.parent_task_id.expected_end_date, 1)
            self.parent_task_id.advance_next_task_to_past_to_follow_replanification(parent_task_initial_end_date,
                                                                                    new_start_date,
                                                                                    only_same_parent_task_if_any=True)

    @api.multi
    def set_task_on_one_day(self):
        for rec in self:
            task_and_children = self.env['project.task'].search([('id', 'child_of', rec.id)])
            initial_end_date = rec.expected_end_date
            new_start_date = rec.expected_start_date
            for task in task_and_children:
                nb_days_start = rec.get_task_number_open_days(rec.expected_start_date, task.expected_start_date) or 0
                nb_days_end = rec.get_task_number_open_days(rec.expected_start_date, task.expected_end_date) or 0
                nb_days_start = max(nb_days_start - 1, 0)
                nb_days_end = max(nb_days_end - 1, 0)
                task.with_context(do_not_propagate_dates=True).write({
                    'forced_duration_one_day': True,
                    'taken_into_account': False,
                    'hidden_from_task_id': rec.id,
                    'nb_days_after_for_start': nb_days_start,
                    'nb_days_after_for_end': nb_days_end,
                })
                task.update_expected_dates_no_write(rec.expected_start_date, rec.expected_start_date)
            rec.advance_next_task_to_past_to_follow_replanification(initial_end_date, new_start_date,
                                                                    only_same_parent_task_if_any=True)

    @api.multi
    def unset_task_on_one_day(self):
        for rec in self:
            if rec.hidden_from_task_id and rec.hidden_from_task_id != rec:
                raise ReDisplayTaskForbidden(rec)
            task_and_children = rec.env['project.task'].search([('id', 'child_of', rec.id)])
            for child in task_and_children:
                # reset_duration_for_tasks is supposed to make only one replanification.
                new_start_date = child.nb_days_after_for_start and rec.schedule_get_date(rec.expected_start_date,
                                                                                         child.nb_days_after_for_start)\
                    or rec.expected_start_date
                new_end_date = child.nb_days_after_for_end and rec.schedule_get_date(rec.expected_start_date,
                                                                                     child.nb_days_after_for_end) or\
                    rec.expected_start_date
                child.update_expected_dates_no_write(new_start_date, new_end_date)
            task_and_children.with_context(propagate_to_the_future=True,
                                           force_dates_changed=True,
                                           do_not_reschedule_task_ids=task_and_children.ids). \
                write({'forced_duration_one_day': False,
                       'hidden_from_task_id': False,
                       'nb_days_after_for_start': 0,
                       'nb_days_after_for_end': 0})
            rec.project_id.update_dates_parent_tasks()
