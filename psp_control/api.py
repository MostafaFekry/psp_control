# -*- coding: utf-8 -*-
# Copyright (c) 2017, Direction and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe, erpnext
from frappe.utils import flt, cstr, nowdate, comma_and
from frappe import throw, msgprint, _
from psp_control.psp_control.doctype.collect_production_item.collect_production_item import check_item_material, cpi_update_status

def stock_entry_before_submit(self, method):
	stock_entry_type= self.stock_entry_type
	def check_reserved_item_controller_user():
		# If not authorized person raise exception
		reserved_item_controller = frappe.db.get_value('PSP Settings', None, 'reserved_item_controller')
		if not reserved_item_controller or reserved_item_controller not in frappe.get_roles():
			throw(_("Please contact to the user who have Reserved Item Manager {0} role")
				.format(" / " + reserved_item_controller if reserved_item_controller else ""))

	if stock_entry_type == 'Send To Reserved':
		collect_production_item = self.collect_production_item
		if not collect_production_item:
			frappe.throw(_("Error. Value missing in: Collect Production Item"))
		doc_collect_production_item = frappe.get_doc('Collect Production Item', collect_production_item)
		doc_collect_production_item_materials = frappe.get_all("Collect Production Item Materials",
			fields=['name', 'item_code', 'stock_qty', 'reserved_qty_at_reserve_warehouse', 'transferred_qty_to_wip_warehouse'],
			filters={"parent": collect_production_item}, order_by="idx asc")
		if not self.from_warehouse == doc_collect_production_item.default_source_warehouse:
			frappe.throw(_("Error. Default Source Warehouse: must be set as {0}").format(doc_collect_production_item.default_source_warehouse))
		if not self.to_warehouse == doc_collect_production_item.reserve_warehouse:
			frappe.throw(_("Error. Default Target Warehouse: must be set as {0}").format(doc_collect_production_item.reserve_warehouse))
		for sn_child_item in self.items:
			if not sn_child_item.s_warehouse == doc_collect_production_item.default_source_warehouse:
				frappe.throw(_("Error. Default Source Warehouse: must be set as {0}").format(doc_collect_production_item.default_source_warehouse))
			if not sn_child_item.t_warehouse == doc_collect_production_item.reserve_warehouse:
				frappe.throw(_("Error. Default Target Warehouse: must be set as {0}").format(doc_collect_production_item.reserve_warehouse))

			doc_collect_production_item_materials = check_item_material(sn_child_item.item_code,collect_production_item)
			if doc_collect_production_item_materials:
				for cpi_child_item in doc_collect_production_item_materials:
					if sn_child_item.item_code == cpi_child_item.get("item_code"):
						if not sn_child_item.collect_production_item_materials == cpi_child_item.get("name"):
							frappe.throw(_("Row({1}): Cannot submit with Item ({0}) not connected by Collect Production Item document.").format(sn_child_item.item_code,sn_child_item.idx,qty))
						qty = cpi_child_item.get("stock_qty") - cpi_child_item.get("reserved_qty_at_reserve_warehouse") - cpi_child_item.get("transferred_qty_to_wip_warehouse")
						if not sn_child_item.transfer_qty <= qty:
							frappe.throw(_("Row({1}): Item ({0}) cannot reserved more than ({2})").format(sn_child_item.item_code,sn_child_item.idx,qty))
			else:
				frappe.throw(_("Row({1}): Item ({0}) not exist on Collect Production Item Materials selected").format(sn_child_item.item_code,sn_child_item.idx))

		check_reserved_item_controller_user()

	if stock_entry_type == 'Return From Reserved':
		collect_production_item = self.collect_production_item
		if not collect_production_item:
			frappe.throw(_("Error. Value missing in: Collect Production Item"))

		doc_collect_production_item = frappe.get_doc('Collect Production Item', collect_production_item)

		doc_collect_production_item_materials = frappe.get_all("Collect Production Item Materials",
			fields=['name', 'item_code', 'stock_qty', 'reserved_qty_at_reserve_warehouse', 'transferred_qty_to_wip_warehouse'],
			filters={"parent": collect_production_item}, order_by="idx asc")

		if not self.from_warehouse == doc_collect_production_item.reserve_warehouse:
			frappe.throw(_("Error. Default Source Warehouse: must be set as {0}").format(doc_collect_production_item.reserve_warehouse))
		if not self.to_warehouse  == doc_collect_production_item.default_source_warehouse:
			frappe.throw(_("Error. Default Target Warehouse: must be set as {0}").format(doc_collect_production_item.default_source_warehouse))

		for sn_child_item in self.items:
			if not sn_child_item.s_warehouse == doc_collect_production_item.reserve_warehouse:
				frappe.throw(_("Error. Default Source Warehouse: must be set as {0}").format(doc_collect_production_item.reserve_warehouse))
			if not sn_child_item.t_warehouse == doc_collect_production_item.default_source_warehouse:
				frappe.throw(_("Error. Default Target Warehouse: must be set as {0}").format(doc_collect_production_item.default_source_warehouse))

			doc_collect_production_item_materials = check_item_material(sn_child_item.item_code,collect_production_item)
			if doc_collect_production_item_materials:
				for cpi_child_item in doc_collect_production_item_materials:
					if sn_child_item.item_code == cpi_child_item.get("item_code"):
						if not sn_child_item.collect_production_item_materials == cpi_child_item.get("name"):
							frappe.throw(_("Row({1}): Cannot submit with Item ({0}) not connected by Collect Production Item document.").format(sn_child_item.item_code,sn_child_item.idx,qty))

						qty = cpi_child_item.get("reserved_qty_at_reserve_warehouse")
						if not sn_child_item.transfer_qty <= qty:
							frappe.throw(_("Row({1}): Item ({0}) cannot return more than ({2})").format(sn_child_item.item_code,sn_child_item.idx,qty))
			else:
				frappe.throw(_("Row({1}): Item ({0}) not exist on Collect Production Item Materials selected").format(sn_child_item.item_code,sn_child_item.idx))

		check_reserved_item_controller_user()

	if stock_entry_type == 'Send To WIP':
		collect_production_item = self.collect_production_item
		if not collect_production_item:
			frappe.throw(_("Error. Value missing in: Collect Production Item"))

		doc_collect_production_item = frappe.get_doc('Collect Production Item', collect_production_item)

		doc_collect_production_item_materials = frappe.get_all("Collect Production Item Materials",
			fields=['name', 'item_code', 'stock_qty', 'reserved_qty_at_reserve_warehouse', 'transferred_qty_to_wip_warehouse'],
			filters={"parent": collect_production_item}, order_by="idx asc")

		if not self.from_warehouse == doc_collect_production_item.reserve_warehouse:
			frappe.throw(_("Error. Default Source Warehouse: must be set as {0}").format(doc_collect_production_item.reserve_warehouse))
		if not self.to_warehouse  == doc_collect_production_item.wip_warehouse:
			frappe.throw(_("Error. Default Target Warehouse: must be set as {0}").format(doc_collect_production_item.wip_warehouse))

		for sn_child_item in self.items:
			if not sn_child_item.s_warehouse == doc_collect_production_item.reserve_warehouse:
				frappe.throw(_("Error. Default Source Warehouse: must be set as {0}").format(doc_collect_production_item.reserve_warehouse))
			if not sn_child_item.t_warehouse == doc_collect_production_item.wip_warehouse:
				frappe.throw(_("Error. Default Target Warehouse: must be set as {0}").format(doc_collect_production_item.wip_warehouse))

			doc_collect_production_item_materials = check_item_material(sn_child_item.item_code,collect_production_item)
			if doc_collect_production_item_materials:
				for cpi_child_item in doc_collect_production_item_materials:
					if sn_child_item.item_code == cpi_child_item.get("item_code"):
						if not sn_child_item.collect_production_item_materials == cpi_child_item.get("name"):
							frappe.throw(_("Row({1}): Cannot submit with Item ({0}) not connected by Collect Production Item document.").format(sn_child_item.item_code,sn_child_item.idx,qty))

						qty = cpi_child_item.get("reserved_qty_at_reserve_warehouse")
						if not sn_child_item.transfer_qty <= qty:
							frappe.throw(_("Row({1}): Item ({0}) cannot return more than ({2})").format(sn_child_item.item_code,sn_child_item.idx,qty))
			else:
				frappe.throw(_("Row({1}): Item ({0}) not exist on Collect Production Item Materials selected").format(sn_child_item.item_code,sn_child_item.idx))

	if stock_entry_type == 'Return From WIP':
		collect_production_item = self.collect_production_item
		if not collect_production_item:
			frappe.throw(_("Error. Value missing in: Collect Production Item"))

		doc_collect_production_item = frappe.get_doc('Collect Production Item', collect_production_item)

		doc_collect_production_item_materials = frappe.get_all("Collect Production Item Materials",
			fields=['name', 'item_code', 'stock_qty', 'reserved_qty_at_reserve_warehouse', 'transferred_qty_to_wip_warehouse'],
			filters={"parent": collect_production_item}, order_by="idx asc")

		if not self.from_warehouse == doc_collect_production_item.wip_warehouse:
			frappe.throw(_("Error. Default Source Warehouse: must be set as {0}").format(doc_collect_production_item.wip_warehouse))
		if not self.to_warehouse  == doc_collect_production_item.default_source_warehouse:
			frappe.throw(_("Error. Default Target Warehouse: must be set as {0}").format(doc_collect_production_item.default_source_warehouse))

		for sn_child_item in self.items:
			if not sn_child_item.s_warehouse == doc_collect_production_item.wip_warehouse:
				frappe.throw(_("Error. Default Source Warehouse: must be set as {0}").format(doc_collect_production_item.wip_warehouse))
			if not sn_child_item.t_warehouse == doc_collect_production_item.default_source_warehouse:
				frappe.throw(_("Error. Default Target Warehouse: must be set as {0}").format(doc_collect_production_item.default_source_warehouse))

			doc_collect_production_item_materials = check_item_material(sn_child_item.item_code,collect_production_item)
			if doc_collect_production_item_materials:
				for cpi_child_item in doc_collect_production_item_materials:
					if sn_child_item.item_code == cpi_child_item.get("item_code"):
						if not sn_child_item.collect_production_item_materials == cpi_child_item.get("name"):
							frappe.throw(_("Row({1}): Cannot submit with Item ({0}) not connected by Collect Production Item document.").format(sn_child_item.item_code,sn_child_item.idx,qty))

						qty = cpi_child_item.get("transferred_qty_to_wip_warehouse")
						if not sn_child_item.transfer_qty <= qty:
							frappe.throw(_("Row({1}): Item ({0}) cannot return more than ({2})").format(sn_child_item.item_code,sn_child_item.idx,qty))
			else:
				frappe.throw(_("Row({1}): Item ({0}) not exist on Collect Production Item Materials selected").format(sn_child_item.item_code,sn_child_item.idx))




def stock_entry_on_submit(self, method):
	stock_entry_type= self.stock_entry_type
	if stock_entry_type == 'Send To Reserved':
		for sn_child_item in self.items:
			cpi_child_item = frappe.get_doc('Collect Production Item Materials', sn_child_item.collect_production_item_materials)
			reserved_qty_at_reserve_warehouse = cpi_child_item.reserved_qty_at_reserve_warehouse + sn_child_item.transfer_qty
			cpi_child_item.db_set('reserved_qty_at_reserve_warehouse', reserved_qty_at_reserve_warehouse, update_modified=False)
		cpi_update_status(self.collect_production_item)
	if stock_entry_type == 'Return From Reserved':
		for sn_child_item in self.items:
			cpi_child_item = frappe.get_doc('Collect Production Item Materials', sn_child_item.collect_production_item_materials)
			reserved_qty_at_reserve_warehouse = cpi_child_item.reserved_qty_at_reserve_warehouse - sn_child_item.transfer_qty
			cpi_child_item.db_set('reserved_qty_at_reserve_warehouse', reserved_qty_at_reserve_warehouse, update_modified=False)
		cpi_update_status(self.collect_production_item)
	if stock_entry_type == 'Send To WIP':
		for sn_child_item in self.items:
			cpi_child_item = frappe.get_doc('Collect Production Item Materials', sn_child_item.collect_production_item_materials)
			reserved_qty_at_reserve_warehouse = cpi_child_item.reserved_qty_at_reserve_warehouse - sn_child_item.transfer_qty
			cpi_child_item.db_set('reserved_qty_at_reserve_warehouse', reserved_qty_at_reserve_warehouse, update_modified=False)
			transferred_qty_to_wip_warehouse = cpi_child_item.transferred_qty_to_wip_warehouse + sn_child_item.transfer_qty
			cpi_child_item.db_set('transferred_qty_to_wip_warehouse', transferred_qty_to_wip_warehouse, update_modified=False)
		cpi_update_status(self.collect_production_item)
	if stock_entry_type == 'Return From WIP':
		for sn_child_item in self.items:
			cpi_child_item = frappe.get_doc('Collect Production Item Materials', sn_child_item.collect_production_item_materials)
			transferred_qty_to_wip_warehouse = cpi_child_item.transferred_qty_to_wip_warehouse - sn_child_item.transfer_qty
			cpi_child_item.db_set('transferred_qty_to_wip_warehouse', transferred_qty_to_wip_warehouse, update_modified=False)
		cpi_update_status(self.collect_production_item)
	if stock_entry_type == 'Manufacture':
		collect_production_item = self.collect_production_item
		if collect_production_item:
			cpi_doc = frappe.get_doc('Collect Production Item', collect_production_item)
			if cpi_doc.status == 'To Finish Good':
				cpi_doc.db_set('status', 'Completed')

def stock_entry_on_cancel(self, method):
	#frappe.throw(_("Under working"))

	return

def bom_on_submit(self, method):
	collect_production_item = self.collect_production_item
	if collect_production_item:
			cpi_doc = frappe.get_doc('Collect Production Item', collect_production_item)
			if cpi_doc.status == 'To BOM':
				cpi_doc.db_set('status', 'To Work Order')

def bom_on_cancel(self, method):
	collect_production_item = self.collect_production_item
	if collect_production_item:
			cpi_doc = frappe.get_doc('Collect Production Item', collect_production_item)
			if cpi_doc.status == 'To Work Order':
				cpi_doc.db_set('status', 'To BOM')
			else:
				frappe.throw(_("Can't cancel BOM, Collect Production Item status is not To Work Order status."))

def work_order_on_submit(self, method):
	collect_production_item = self.collect_production_item
	if collect_production_item:
			cpi_doc = frappe.get_doc('Collect Production Item', collect_production_item)
			if cpi_doc.status == 'To Work Order':
				cpi_doc.db_set('status', 'To Finish Good')

def work_order_on_cancel(self, method):
	collect_production_item = self.collect_production_item
	if collect_production_item:
			cpi_doc = frappe.get_doc('Collect Production Item', collect_production_item)
			if cpi_doc.status == 'To Finish Good':
				cpi_doc.db_set('status', 'To Work Order')
			else:
				frappe.throw(_("Can't cancel Work Order, Collect Production Item status is not TTo Finish Good."))
