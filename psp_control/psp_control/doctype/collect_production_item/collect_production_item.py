# -*- coding: utf-8 -*-
# Copyright (c) 2019, Systematic-eg and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
import json
import frappe, erpnext
from frappe.utils import cint, cstr, flt, nowdate, get_link_to_form
from frappe.model.document import Document
from frappe import _
from erpnext.setup.utils import get_exchange_rate
from erpnext.stock.get_item_details import get_conversion_factor
from erpnext.stock.utils import get_bin, validate_warehouse_company, get_latest_stock_qty
from frappe.desk.notifications import clear_doctype_notifications
from frappe.model.mapper import get_mapped_doc
from frappe.desk.form.utils import add_comment

import functools

from six import string_types

from operator import itemgetter

class CollectProductionItem(Document):
	def autoname(self):
		names = frappe.db.sql_list("""select name from `tabCollect Production Item` where item=%s""", self.item)

		if names:
			# name can be CIP-BOM/ITEM/001, CIP-BOM/ITEM/001-1, CIP-BOM-ITEM-001, CIP-BOM-ITEM-001-1

			# split by item
			names = [name.split(self.item)[-1][1:] for name in names]

			# split by (-) if cancelled
			names = [cint(name.split('-')[-1]) for name in names]

			idx = max(names) + 1
		else:
			idx = 1

		self.name = 'CIP-BOM-' + self.item + ('-%.3i' % idx)
	
	
	def validate(self):
		self.validate_main_item()
		self.set_conversion_rate()
		self.validate_uom_is_interger()
		self.set_bom_material_details()
		self.validate_materials()
		self.calculate_cost()
		self.validate_sales_order()
		self.validate_default_warehouse()

		
		if not self.reserved_status: self.reserved_status = 'Not Reserved'
		if not self.transferred_status: self.transferred_status = 'Not Transferred'
		self.status = self.get_status()
	
	def on_update(self):
		self.update_stock_qty()
	
	def update_stock_qty(self):
		for m in self.get('items'):
			if not m.conversion_factor:
				m.conversion_factor = flt(get_conversion_factor(m.item_code, m.uom)['conversion_factor'])
			if m.uom and m.qty:
				m.stock_qty = flt(m.conversion_factor)*flt(m.qty)
			if not m.uom and m.stock_uom:
				m.uom = m.stock_uom
				m.qty = m.stock_qty

			m.db_update()
	
	
	def validate_main_item(self):
		""" Validate main FG item"""
		item = self.get_item_det(self.item)
		if not item:
			frappe.throw(_("Item {0} does not exist in the system or has expired").format(self.item))
		else:
			ret = frappe.db.get_value("Item", self.item, ["description", "stock_uom", "item_name", "is_stock_item"])
			self.description = ret[0]
			self.uom = ret[1]
			self.item_name= ret[2]
			self.is_stock_item= ret[3]

		if not self.quantity:
			frappe.throw(_("Quantity should be greater than 0"))
	
	def set_conversion_rate(self):
		if self.currency == self.company_currency():
			self.conversion_rate = 1
		elif self.conversion_rate == 1 or flt(self.conversion_rate) <= 0:
			self.conversion_rate = get_exchange_rate(self.currency, self.company_currency(), args="for_buying")
	
	def validate_uom_is_interger(self):
		from erpnext.utilities.transaction_base import validate_uom_is_integer
		validate_uom_is_integer(self, "uom", "qty", "Collect Production Item Materials")
		validate_uom_is_integer(self, "stock_uom", "stock_qty", "Collect Production Item Materials")



	def validate_default_warehouse(self):
		default_source_warehouse = frappe.db.get_single_value("PSP Settings",
			"default_source_warehouse")
		if not default_source_warehouse:
			frappe.throw(_("Default Source Warehouse not defined in PSP Settings"))
		self.default_source_warehouse = default_source_warehouse
		
		wip_warehouse = frappe.db.get_single_value("Manufacturing Settings",
			"default_wip_warehouse")
		if not wip_warehouse:
			frappe.throw(_("Default Work in Progress Warehouse not defined in Manufacturing Settings"))
		self.wip_warehouse = wip_warehouse
		
		reserve_warehouse = frappe.db.get_single_value("PSP Settings",
			"default_reserve_warehouse")
		if not reserve_warehouse:
			frappe.throw(_("Default Reserve Warehouse not defined in PSP Settings"))
		self.reserve_warehouse = reserve_warehouse
		
	def set_bom_material_details(self):
		for item in self.get("items"):

			ret = self.get_bom_material_detail({
				"item_code": item.item_code,
				"item_name": item.item_name,
				"is_stock_item": item.is_stock_item,
				"stock_qty": item.stock_qty,
				"qty": item.qty,
				"uom": item.uom,
				"stock_uom": item.stock_uom,
				"conversion_factor": item.conversion_factor
			})
			for r in ret:
				if not item.get(r):
					item.set(r, ret[r])
		
		self.set_available_qty()
	
	def set_available_qty(self):
		for d in self.get("items"):
			if self.default_source_warehouse:
				d.available_qty_at_source_warehouse = get_latest_stock_qty(d.item_code, self.default_source_warehouse)
				
	def validate_materials(self):
		""" Validate raw material entries """

		def get_duplicates(lst):
			seen = set()
			seen_add = seen.add
			for item in lst:
				if item.item_code in seen or seen_add(item.item_code):
					yield item

		if not self.get('items'):
			frappe.throw(_("Raw Materials cannot be blank."))
		check_list = []
		for m in self.get('items'):
			if flt(m.qty) <= 0:
				frappe.throw(_("Quantity required for Item {0} in row {1}").format(m.item_code, m.idx))
			check_list.append(m)

		
		duplicate_items = list(get_duplicates(check_list))
		if duplicate_items:
			li = []
			for i in duplicate_items:
				li.append("{0} on row {1}".format(i.item_code, i.idx))
			duplicate_list = '<br>' + '<br>'.join(li)

			frappe.throw(_("Same item has been entered multiple times. {0}").format(duplicate_list))
				
	
	def get_bom_material_detail(self, args=None):
		""" Get raw material details like uom, desc and rate"""
		if not args:
			args = frappe.form_dict.get('args')

		if isinstance(args, string_types):
			import json
			args = json.loads(args)

		item = self.get_item_det(args['item_code'])
		self.validate_rm_item(item)

		args.update(item[0])

		rate = self.get_rm_rate(args)
		ret_item = {
			 'item_name'	: item and args['item_name'] or '',
			 'is_stock_item': item and args['is_stock_item'] or '',
			 'description'  : item and args['description'] or '',
			 'image'		: item and args['image'] or '',
			 'stock_uom'	: item and args['stock_uom'] or '',
			 'uom'			: item and args['stock_uom'] or '',
 			 'conversion_factor': 1,
			 'rate'			: rate,
			 'qty'			: args.get("qty") or args.get("stock_qty") or 1,
			 'stock_qty'	: args.get("qty") or args.get("stock_qty") or 1,
			 'base_rate'	: rate
		}

		return ret_item
	
	def get_item_det(self, item_code):
		item = frappe.db.sql("""select name, item_name, docstatus, description, image,
			is_sub_contracted_item,is_stock_item, stock_uom, default_bom, last_purchase_rate, include_item_in_manufacturing
			from `tabItem` where name=%s""", item_code, as_dict = 1)

		if not item:
			frappe.throw(_("Item: {0} does not exist in the system").format(item_code))

		return item
	
	def get_rm_rate(self, arg):
		"""	Get raw material rate as per selected method, if bom exists takes bom cost """
		rate = 0
		if not self.rm_cost_as_per:
			self.rm_cost_as_per = "Valuation Rate"

		if arg:
			#Customer Provided parts will have zero rate
			if not frappe.db.get_value('Item', arg["item_code"], 'is_customer_provided_item'):
				if self.rm_cost_as_per == 'Valuation Rate':
					rate = self.get_valuation_rate(arg) * (arg.get("conversion_factor") or 1)
				elif self.rm_cost_as_per == 'Last Purchase Rate':
					rate = (arg.get('last_purchase_rate') \
						or frappe.db.get_value("Item", arg['item_code'], "last_purchase_rate")) \
							* (arg.get("conversion_factor") or 1)

				if not rate:
					frappe.msgprint(_("{0} not found for item {1}")
						.format(self.rm_cost_as_per, arg["item_code"]), alert=True)

		return flt(rate) / (self.conversion_rate or 1)
	
	def update_cost(self, update_parent=True, from_child_bom=False, save=True):
		if self.docstatus == 2:
			return

		existing_bom_cost = self.total_cost

		for d in self.get("items"):
			rate = self.get_rm_rate({
				"item_code": d.item_code,
				"qty": d.qty,
				"uom": d.uom,
				"stock_uom": d.stock_uom,
				"conversion_factor": d.conversion_factor
			})
			if rate:
				d.rate = rate
			d.amount = flt(d.rate) * flt(d.qty)

		self.set_available_qty()
		
		if self.docstatus == 1:
			self.flags.ignore_validate_update_after_submit = True
			self.calculate_cost()
		#if save:
			self.save()


		#if not from_child_bom:
			#frappe.msgprint(_("Available Qty and Cost Updated"))
	
	def get_valuation_rate(self, args):
		""" Get weighted average of valuation rate from all warehouses """

		total_qty, total_value, valuation_rate = 0.0, 0.0, 0.0
		for d in frappe.db.sql("""select actual_qty, stock_value from `tabBin`
			where item_code=%s""", args['item_code'], as_dict=1):
				total_qty += flt(d.actual_qty)
				total_value += flt(d.stock_value)

		if total_qty:
			valuation_rate =  total_value / total_qty

		if valuation_rate <= 0:
			last_valuation_rate = frappe.db.sql("""select valuation_rate
				from `tabStock Ledger Entry`
				where item_code = %s and valuation_rate > 0
				order by posting_date desc, posting_time desc, creation desc limit 1""", args['item_code'])

			valuation_rate = flt(last_valuation_rate[0][0]) if last_valuation_rate else 0

		if not valuation_rate:
			valuation_rate = frappe.db.get_value("Item", args['item_code'], "valuation_rate")

		return valuation_rate
		
	def validate_rm_item(self, item):
		if (item[0]['name'] in [it.item_code for it in self.items]) and item[0]['name'] == self.item:
			frappe.throw(_("Collect Production Item - BOM #{0}: Raw material cannot be same as main Item").format(self.name))
	
	
	def calculate_cost(self):
		"""Calculate bom totals"""
		self.calculate_rm_cost()
		self.total_cost = self.raw_material_cost
		self.base_total_cost = self.base_raw_material_cost
	
	def calculate_rm_cost(self):
		"""Fetch RM rate as per today's valuation rate and calculate totals"""
		total_rm_cost = 0
		base_total_rm_cost = 0

		for d in self.get('items'):
			d.base_rate = flt(d.rate) * flt(self.conversion_rate)
			d.amount = flt(d.rate, d.precision("rate")) * flt(d.qty, d.precision("qty"))
			d.base_amount = d.amount * flt(self.conversion_rate)
			d.qty_consumed_per_unit = flt(d.stock_qty, d.precision("stock_qty")) \
				/ flt(self.quantity, self.precision("quantity"))

			total_rm_cost += d.amount
			base_total_rm_cost += d.base_amount

		self.raw_material_cost = total_rm_cost
		self.base_raw_material_cost = base_total_rm_cost
	
	def company_currency(self):
		return erpnext.get_company_currency(self.company)


	def validate_sales_order(self):
		if self.sales_order:
			self.check_sales_order_on_hold_or_close()
			so = frappe.db.sql("""
				select so.name, so_item.delivery_date, so.project
				from `tabSales Order` so
				inner join `tabSales Order Item` so_item on so_item.parent = so.name
				left join `tabProduct Bundle Item` pk_item on so_item.item_code = pk_item.parent
				where so.name=%s and so.docstatus = 1 and (
					so_item.item_code=%s or
					pk_item.item_code=%s )
			""", (self.sales_order, self.item, self.item), as_dict=1)

			if not so:
				so = frappe.db.sql("""
					select
						so.name, so_item.delivery_date, so.project
					from
						`tabSales Order` so, `tabSales Order Item` so_item, `tabPacked Item` packed_item
					where so.name=%s
						and so.name=so_item.parent
						and so.name=packed_item.parent
						and so_item.item_code = packed_item.parent_item
						and so.docstatus = 1 and packed_item.item_code=%s
				""", (self.sales_order, self.item), as_dict=1)

			if len(so):
				if not self.expected_delivery_date:
					self.expected_delivery_date = so[0].delivery_date

				if so[0].project:
					self.project = so[0].project

				self.validate_work_order_against_so()
			else:
				frappe.throw(_("Sales Order {0} is not valid").format(self.sales_order))
	
	def check_sales_order_on_hold_or_close(self):
		status = frappe.db.get_value("Sales Order", self.sales_order, "status")
		if status in ("Closed", "On Hold"):
			frappe.throw(_("Sales Order {0} is {1}").format(self.sales_order, status))
	
	def validate_work_order_against_so(self):
		# already ordered qty
		ordered_qty_against_so = frappe.db.sql("""select sum(quantity) from `tabCollect Production Item`
			where item = %s and sales_order = %s and docstatus < 2 and name != %s""",
			(self.item, self.sales_order, self.name))[0][0]

		total_qty = flt(ordered_qty_against_so) + flt(self.quantity)

		# get qty from Sales Order Item table
		so_item_qty = frappe.db.sql("""select sum(stock_qty) from `tabSales Order Item`
			where parent = %s and item_code = %s""",
			(self.sales_order, self.item))[0][0]
		# get qty from Packing Item table
		dnpi_qty = frappe.db.sql("""select sum(qty) from `tabPacked Item`
			where parent = %s and parenttype = 'Sales Order' and item_code = %s""",
			(self.sales_order, self.item))[0][0]
		# total qty in SO
		so_qty = flt(so_item_qty) + flt(dnpi_qty)

		allowance_percentage = flt(frappe.db.get_single_value("Manufacturing Settings",
			"overproduction_percentage_for_sales_order"))

		if total_qty > so_qty + (allowance_percentage/100 * so_qty):
			frappe.throw(_("Cannot produce more Item {0} than Sales Order quantity {1}")
				.format(self.item, so_qty), OverProductionError)
	
	def check_modified_date(self):
		mod_db = frappe.db.get_value("Collect Production Item", self.name, "modified")
		date_diff = frappe.db.sql("select TIMEDIFF('%s', '%s')" %
			( mod_db, cstr(self.modified)))
		if date_diff and date_diff[0][0]:
			frappe.throw(_("{0} {1} has been modified. Please refresh.").format(self.doctype, self.name))

	
	def update_status(self, status=None):
		self.check_modified_date()
		'''Update status of work order if unknown'''
		if status != "To BOM":
			if status != "On Hold":
				status = self.get_status(status)

		if status != self.status:
			self.db_set("status", status)

		#self.update_required_items()

		return status

	def get_status(self, status=None):
		'''Return the status based on stock entries against this work order'''
		if not status:
			status = self.status

		if self.docstatus==0:
			status = 'Draft'
		elif self.docstatus==1:
			if status != 'On Hold':
				if self.transferred_status == 'Partly Transferred':
					status = "In Process"
				elif self.transferred_status == 'Fully Transferred':
					status = "Waiting for Approval"
				else:
					status = "Not Started"
		else:
			status = 'Cancelled'

		return status

def cpi_update_status(reference_name):
	doc = frappe.get_doc('Collect Production Item', reference_name)
	child_item = frappe.get_all("Collect Production Item Materials",
		fields=["idx","item_code","name","is_stock_item","stock_qty","reserved_qty_at_reserve_warehouse","transferred_qty_to_wip_warehouse"],
		filters={"parent": reference_name}, order_by="idx asc")
	all_qty = 0
	all_reserved_qty = 0
	all_transferred_qty = 0
	for item in child_item:
		if item.get("is_stock_item") == 1:
			all_qty = all_qty + item.get("stock_qty")
			all_reserved_qty = all_reserved_qty + item.get("reserved_qty_at_reserve_warehouse") + item.get("transferred_qty_to_wip_warehouse")
			all_transferred_qty = all_transferred_qty + item.get("transferred_qty_to_wip_warehouse")
	
	all_reserved_qty_prcent = (all_reserved_qty * 100) / all_qty
	if all_reserved_qty_prcent == 0:
		doc.db_set('reserved_status', 'Not Reserved', update_modified=False)	
	elif all_reserved_qty_prcent > 0 and all_reserved_qty_prcent < 100:
		doc.db_set('reserved_status', 'Partly Reserved', update_modified=False)
	elif all_reserved_qty_prcent == 100:
		doc.db_set('reserved_status', 'Fully Reserved', update_modified=False)
	else:
		doc.db_set('reserved_status', 'Not Applicable', update_modified=False)
	doc.db_set('per_reserved', all_reserved_qty_prcent, update_modified=False)
	
	all_transferred_qty_prcent = (all_transferred_qty * 100) / all_qty
	if all_transferred_qty_prcent == 0:
		doc.db_set('transferred_status', 'Not Transferred', update_modified=False)
		doc.db_set('status', 'Not Started')
	elif all_transferred_qty_prcent > 0 and all_transferred_qty_prcent < 100:
		doc.db_set('transferred_status', 'Partly Transferred', update_modified=False)
		doc.db_set('status', 'In Process')
	elif all_transferred_qty_prcent == 100:
		doc.db_set('transferred_status', 'Fully Transferred', update_modified=False)
		doc.db_set('status', 'Waiting for Approval')
	else:
		doc.db_set('transferred_status', 'Not Applicable', update_modified=False)
	doc.db_set('per_transferred', all_transferred_qty_prcent, update_modified=False)
		
		
@frappe.whitelist()
def get_default_warehouse():
	default_source_warehouse = frappe.db.get_single_value("PSP Settings",
		"default_source_warehouse")
	wip_warehouse = frappe.db.get_single_value("Manufacturing Settings",
		"default_wip_warehouse")
	reserve_warehouse = frappe.db.get_single_value("PSP Settings",
		"default_reserve_warehouse")
	return {"default_source_warehouse": default_source_warehouse, "wip_warehouse": wip_warehouse, "reserve_warehouse": reserve_warehouse}

@frappe.whitelist()
def update_status(status, name):
	if not frappe.has_permission("Collect Production Item", "write"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	cpi = frappe.get_doc("Collect Production Item", name)
	status = cpi.update_status(status)
	frappe.msgprint(_("Collect Production Item has been {0}").format(status))
	cpi.notify_update()
	return cpi.status

def get_requested_item_qty(collect_production_item):
	return frappe._dict(frappe.db.sql("""
		select collect_production_item_materials, sum(stock_qty)
		from `tabMaterial Request Item`
		where docstatus = 1
			and collect_production_item = %s
		group by collect_production_item_materials
	""", collect_production_item))
	
def get_material_request(collect_production_item):
	return frappe.db.sql_list("""select t1.name
			from `tabMaterial Request` t1,`tabMaterial Request Item` t2
			where t1.name = t2.parent and t2.collect_production_item = %s and t1.docstatus = 0""",
			collect_production_item)

@frappe.whitelist()
def make_material_request(source_name, target_doc=None):
	requested_item_qty = get_requested_item_qty(source_name)
	check_material_request = get_material_request(source_name)
	if check_material_request:
		check_material_request = [get_link_to_form("Material Request", si) for si in check_material_request]
		frappe.throw(_("Material Request {0} must be submitted before creating new material request")
			.format(", ".join(check_material_request)))

	def postprocess(source, doc):
		doc.material_request_type = "Purchase"

	def update_item(source, target, source_parent):
		# qty is for packed items, because packed items don't have stock_qty field
		qty = source.get("stock_qty") - source.get("reserved_qty_at_reserve_warehouse") - source.get("transferred_qty_to_wip_warehouse") - requested_item_qty.get(source.name, 0) - source.get("available_qty_at_source_warehouse")

		if qty <0:
			qty = 0
			
		target.warehouse = source_parent.default_source_warehouse
		target.project = source_parent.project
		target.qty = qty
		target.conversion_factor = 1
		target.stock_qty = qty
		target.schedule_date = nowdate()

	doc = get_mapped_doc("Collect Production Item", source_name, {
		"Collect Production Item": {
			"doctype": "Material Request",
			"validation": {
				"docstatus": ["=", 1]
			}
		},
		"Collect Production Item Materials": {
			"doctype": "Material Request Item",
			"field_map": {
				"name": "collect_production_item_materials",
				"parent": "collect_production_item",
				"stock_uom": "stock_uom",
				"stock_qty": "stock_qty"
			},
			"condition": lambda doc: ((doc.stock_qty - doc.reserved_qty_at_reserve_warehouse - doc.transferred_qty_to_wip_warehouse - requested_item_qty.get(doc.name, 0) - doc.available_qty_at_source_warehouse) > 0) and doc.is_stock_item == 1,
			"postprocess": update_item
		}
	}, target_doc, postprocess)

	return doc

def set_collect_production_item_defaults(parent_doctype, parent_doctype_name, child_docname, item_code):
	"""
	Returns a Collect Production Item Materials containing the default values
	"""
	p_doctype = frappe.get_doc(parent_doctype, parent_doctype_name)
	child_item = frappe.new_doc('Collect Production Item Materials', p_doctype, child_docname)
	item = frappe.get_doc("Item", item_code)
	child_item.item_code = item.item_code
	child_item.item_name = item.item_name
	child_item.description = item.description
	child_item.uom = item.stock_uom
	child_item.stock_uom = item.stock_uom
	child_item.rate = 0
	child_item.conversion_factor = get_conversion_factor(item_code, item.stock_uom).get("conversion_factor") or 1.0
	return child_item

def check_item_material(item_code,reference_name):
	child_item_name = frappe.get_all("Collect Production Item Materials",
		fields=["item_code","name","idx","stock_qty","reserved_qty_at_reserve_warehouse","transferred_qty_to_wip_warehouse"],
		filters={"parent": reference_name,"item_code": item_code}, order_by="idx asc")
	return child_item_name

@frappe.whitelist()
def make_add_new_material(trans_items, reference_name):
	doc = frappe.get_doc('Collect Production Item', reference_name)
	data  = json.loads(trans_items)

	for item in data:
		new_child_flag = False
		#frappe.throw(_("{0},{1}").format(item.get("item_code"),olditem.get("item_code")))
		child_item_name = check_item_material(item.get("item_code"),reference_name)
		if child_item_name:
			for olditem in child_item_name:
				if item.get("item_code") == olditem.get("item_code"):
					child_item = frappe.get_doc('Collect Production Item Materials', olditem.get("name"))
			old_qty = child_item.qty
			#frappe.throw(_("{0}").format(child_item.qty))
			child_item.qty = flt(item.get("qty")) + flt(child_item.qty)
			if child_item.reserved_qty_at_reserve_warehouse > 0:
				if ((old_qty * child_item.conversion_factor) - child_item.reserved_qty_at_reserve_warehouse - child_item.transferred_qty_to_wip_warehouse) + (flt(item.get("qty"))*child_item.conversion_factor) < 0:
					frappe.throw(_("Error in item {0}, Unable to reduce qty less then 0.").format(child_item.item_code))
			elif child_item.transferred_qty_to_wip_warehouse > 0:
				if ((old_qty * child_item.conversion_factor) - child_item.reserved_qty_at_reserve_warehouse - child_item.transferred_qty_to_wip_warehouse) + (flt(item.get("qty"))*child_item.conversion_factor) < 0:
					frappe.throw(_("Error in item {0}, Unable to reduce qty less then 0.").format(child_item.item_code))
			else:
				if ((old_qty * child_item.conversion_factor) - child_item.reserved_qty_at_reserve_warehouse - child_item.transferred_qty_to_wip_warehouse) + (flt(item.get("qty"))*child_item.conversion_factor) <= 0:
					frappe.throw(_("Error in item {0}, Unable to reduce qty equal or less then 0.").format(child_item.item_code))
			child_item.flags.ignore_validate_update_after_submit = True
			child_item.save()
		else:
			child_item  = set_collect_production_item_defaults('Collect Production Item', reference_name, 'items', item.get("item_code"))
			child_item.qty = flt(item.get("qty"))
			child_item.stock_qty = flt(item.get("qty"))
			child_item.flags.ignore_validate_update_after_submit = True
			child_item.idx = len(doc.items) + 1
			child_item.insert()

	cpi_update_status(reference_name)
	doc.reload()
	doc.flags.ignore_validate_update_after_submit = True
	doc.update_stock_qty()
	doc.set_bom_material_details()
	doc.update_cost()
	doc.save()
	
def delete_item_material(collect_production_item,reference_name,child_item_doc):
	frappe.db.sql("""
		DELETE FROM `tabCollect Production Item Materials` WHERE name = %s and parent = %s
	""", (child_item_doc,reference_name))
def get_all_item_material(reference_name):
	all_item_material = frappe.get_all("Collect Production Item Materials",
		filters={"parent": reference_name}, order_by="idx asc")
	return all_item_material
	
@frappe.whitelist()
def make_remove_item_material(reference_doctype, reference_name,delet_item_code, content, comment_email):
	
	#frappe.throw(_("{0} need to remove").format(delet_item_code))
	child_item_name = check_item_material(delet_item_code,reference_name)
	if child_item_name:
		for child_item in child_item_name:
			if delet_item_code == child_item.get("item_code"):
				if child_item.get("reserved_qty_at_reserve_warehouse") > 0:
					frappe.throw(_("Error: Cannot remove selected item ({0}), Item has ({1}) quantity in Reserve Warehouse.<br>Return quantity to Source Warehouse then remove").format(delet_item_code,child_item.get("reserved_qty_at_reserve_warehouse")))
				if child_item.get("transferred_qty_to_wip_warehouse") > 0:
					frappe.throw(_("Error: Cannot remove selected item ({0}), Item has ({1}) quantity in WIP Warehouse.<br>Return quantity to Source Warehouse then remove").format(delet_item_code,child_item.get("transferred_qty_to_wip_warehouse")))
				#frappe.delete_doc('Collect Production Item Materials', child_item.get("name"))
				delete_item_material('Collect Production Item Materials',reference_name,child_item.get("name"))

		all_item_material = get_all_item_material(reference_name)
		idx_count = 1
		for child_item_old_idx in all_item_material:
			child_item = frappe.get_doc('Collect Production Item Materials', child_item_old_idx.get("name"))
			child_item.db_set('idx', idx_count, update_modified=False)
			idx_count = idx_count + 1
	else:
		frappe.throw(_("Selected item ({0}) not at Material Items").format(delet_item_code))
		
	cpi_update_status(reference_name)
	add_new_comment = add_comment(reference_doctype, reference_name, content, comment_email)
	doc = frappe.get_doc('Collect Production Item', reference_name)
	doc.reload()
	doc.flags.ignore_validate_update_after_submit = True
	doc.update_stock_qty()
	doc.set_bom_material_details()
	doc.update_cost()
	doc.save()
	return add_new_comment
	


def get_stock_entry_qty(collect_production_item):
	return frappe._dict(frappe.db.sql("""
		select collect_production_item_materials, sum(stock_qty)
		from `tabMaterial Request Item`
		where docstatus = 1
			and collect_production_item = %s
		group by collect_production_item_materials
	""", collect_production_item))
	
def get_stock_entry(collect_production_item,purpose):
	return frappe.db.sql_list("""select t1.name , sum(t2.transfer_qty)
			from `tabStock Entry` t1,`tabStock Entry Detail` t2
			where t1.name = t2.parent and t1.collect_production_item = %s  and t2.collect_production_item = %s and t1.docstatus = 0 group by t1.name """,(
			collect_production_item,collect_production_item))

@frappe.whitelist()
def make_stock_entry_send_to_reserved(reference_name, target_doc=None):
	check_stock_entry = get_stock_entry(reference_name,'Send To Reserved')
	if check_stock_entry:
		check_stock_entry = [get_link_to_form("Stock Entry", si) for si in check_stock_entry]
		frappe.throw(_("Stock Entry {0} must be submitted before creating new stock entry")
			.format(", ".join(check_stock_entry)))

	def postprocess(source, doc):
		doc.stock_entry_type = "Send To Reserved"
		doc.purpose = "Material Transfer"
		doc.from_warehouse = frappe.db.get_single_value("PSP Settings",
		"default_source_warehouse")
		doc.to_warehouse = frappe.db.get_single_value("PSP Settings",
		"default_reserve_warehouse")

	def update_item(source, target, source_parent):
		# qty is for packed items, because packed items don't have stock_qty field
		qty = source.get("stock_qty") - source.get("reserved_qty_at_reserve_warehouse") - source.get("transferred_qty_to_wip_warehouse")
		if qty > source.get("available_qty_at_source_warehouse"):
			qty = source.get("available_qty_at_source_warehouse")

		if qty <0:
			qty = 0
			
		target.s_warehouse = source_parent.default_source_warehouse
		target.t_warehouse = source_parent.reserve_warehouse
		target.project = source_parent.project
		target.qty = qty
		target.conversion_factor = 1
		target.transfer_qty = qty
		target.uom = source.get("stock_uom")

	doc = get_mapped_doc("Collect Production Item", reference_name, {
		"Collect Production Item": {
		"doctype": "Stock Entry",
		"validation": {
			"docstatus": ["=", 1]
		}
	},
		"Collect Production Item Materials": {
			"doctype": "Stock Entry Detail",
			"field_map": {
				"name": "collect_production_item_materials",
				"parent": "collect_production_item",
				"stock_uom": "stock_uom",
				"stock_qty": "stock_qty"
			},
			"condition": lambda doc: 	(doc.stock_qty - doc.reserved_qty_at_reserve_warehouse - doc.transferred_qty_to_wip_warehouse > 0) and doc.is_stock_item == 1,
			"postprocess": update_item
		}
	}, target_doc, postprocess)
	 #and ((doc.stock_qty - doc.reserved_qty_at_reserve_warehouse - doc.transferred_qty_to_wip_warehouse) <= doc.available_qty_at_source_warehouse)
	return doc

@frappe.whitelist()
def make_stock_entry_return_from_reserved(reference_name, target_doc=None):
	check_stock_entry = get_stock_entry(reference_name,'Send To Reserved')
	if check_stock_entry:
		check_stock_entry = [get_link_to_form("Stock Entry", si) for si in check_stock_entry]
		frappe.throw(_("Stock Entry {0} must be submitted before creating new stock entry")
			.format(", ".join(check_stock_entry)))

	def postprocess(source, doc):
		doc.stock_entry_type = "Return From Reserved"
		doc.purpose = "Material Transfer"
		doc.from_warehouse = frappe.db.get_single_value("PSP Settings",
		"default_reserve_warehouse")
		doc.to_warehouse = frappe.db.get_single_value("PSP Settings",
		"default_source_warehouse")

	def update_item(source, target, source_parent):
		# qty is for packed items, because packed items don't have stock_qty field
		qty = source.get("reserved_qty_at_reserve_warehouse")
			
		target.s_warehouse = source_parent.reserve_warehouse
		target.t_warehouse = source_parent.default_source_warehouse
		target.project = source_parent.project
		target.qty = qty
		target.conversion_factor = 1
		target.transfer_qty = qty
		target.uom = source.get("stock_uom")

	doc = get_mapped_doc("Collect Production Item", reference_name, {
		"Collect Production Item": {
		"doctype": "Stock Entry",
		"validation": {
			"docstatus": ["=", 1]
		}
	},
		"Collect Production Item Materials": {
			"doctype": "Stock Entry Detail",
			"field_map": {
				"name": "collect_production_item_materials",
				"parent": "collect_production_item",
				"stock_uom": "stock_uom",
				"stock_qty": "stock_qty"
			},
			"condition": lambda doc: (doc.stock_qty > 0) and doc.is_stock_item == 1,
			"postprocess": update_item
		}
	}, target_doc, postprocess)

	return doc	

@frappe.whitelist()
def make_stock_entry_send_to_wip(reference_name, target_doc=None):
	check_stock_entry = get_stock_entry(reference_name,'Send To Reserved')
	if check_stock_entry:
		check_stock_entry = [get_link_to_form("Stock Entry", si) for si in check_stock_entry]
		frappe.throw(_("Stock Entry {0} must be submitted before creating new stock entry")
			.format(", ".join(check_stock_entry)))

	def postprocess(source, doc):
		doc.stock_entry_type = "Send To WIP"
		doc.purpose = "Material Transfer"
		doc.from_warehouse = frappe.db.get_single_value("PSP Settings",
		"default_reserve_warehouse")
		doc.to_warehouse = frappe.db.get_single_value("Manufacturing Settings",
		"default_wip_warehouse")

	def update_item(source, target, source_parent):
		# qty is for packed items, because packed items don't have stock_qty field
		qty = source.get("reserved_qty_at_reserve_warehouse")
			
		target.s_warehouse = source_parent.reserve_warehouse
		target.t_warehouse = source_parent.wip_warehouse
		target.project = source_parent.project
		target.qty = qty
		target.conversion_factor = 1
		target.transfer_qty = qty
		target.uom = source.get("stock_uom")

	doc = get_mapped_doc("Collect Production Item", reference_name, {
		"Collect Production Item": {
		"doctype": "Stock Entry",
		"validation": {
			"docstatus": ["=", 1]
		}
	},
		"Collect Production Item Materials": {
			"doctype": "Stock Entry Detail",
			"field_map": {
				"name": "collect_production_item_materials",
				"parent": "collect_production_item",
				"stock_uom": "stock_uom",
				"stock_qty": "stock_qty"
			},
			"condition": lambda doc: (doc.reserved_qty_at_reserve_warehouse > 0) and doc.is_stock_item == 1,
			"postprocess": update_item
		}
	}, target_doc, postprocess)

	return doc
	
@frappe.whitelist()
def make_stock_entry_return_from_wip(reference_name, target_doc=None):
	check_stock_entry = get_stock_entry(reference_name,'Send To Reserved')
	if check_stock_entry:
		check_stock_entry = [get_link_to_form("Stock Entry", si) for si in check_stock_entry]
		frappe.throw(_("Stock Entry {0} must be submitted before creating new stock entry")
			.format(", ".join(check_stock_entry)))

	def postprocess(source, doc):
		doc.stock_entry_type = "Return From WIP"
		doc.purpose = "Material Transfer"
		doc.from_warehouse = frappe.db.get_single_value("Manufacturing Settings",
		"default_wip_warehouse")
		doc.to_warehouse = frappe.db.get_single_value("PSP Settings",
		"default_source_warehouse")

	def update_item(source, target, source_parent):
		# qty is for packed items, because packed items don't have stock_qty field
		qty = source.get("transferred_qty_to_wip_warehouse")
			
		target.s_warehouse = source_parent.wip_warehouse
		target.t_warehouse = source_parent.default_source_warehouse
		target.project = source_parent.project
		target.qty = qty
		target.conversion_factor = 1
		target.transfer_qty = qty
		target.uom = source.get("stock_uom")

	doc = get_mapped_doc("Collect Production Item", reference_name, {
		"Collect Production Item": {
		"doctype": "Stock Entry",
		"validation": {
			"docstatus": ["=", 1]
		}
	},
		"Collect Production Item Materials": {
			"doctype": "Stock Entry Detail",
			"field_map": {
				"name": "collect_production_item_materials",
				"parent": "collect_production_item",
				"stock_uom": "stock_uom",
				"stock_qty": "stock_qty"
			},
			"condition": lambda doc: (doc.transferred_qty_to_wip_warehouse > 0) and doc.is_stock_item == 1,
			"postprocess": update_item
		}
	}, target_doc, postprocess)

	return doc

def get_bom(collect_production_item):
	return frappe.db.sql_list("""select t1.name , sum(t2.qty)
			from `tabBOM` t1,`tabBOM Item` t2
			where t1.name = t2.parent and t1.collect_production_item = %s  and t2.collect_production_item = %s and t1.docstatus < 2  group by t1.name """,(
			collect_production_item,collect_production_item))
@frappe.whitelist()
def make_bom(reference_name, target_doc=None):
	check_make_bom = get_bom(reference_name)
	if check_make_bom:
		check_make_bom = [get_link_to_form("BOM", si) for si in check_make_bom]
		frappe.throw(_("BOM {0} created.")
			.format(", ".join(check_make_bom)))

	#def postprocess(source, doc):
		

	def update_item(source, target, source_parent):
			
		target.collect_production_item = source_parent.name
		target.source_warehouse = source_parent.wip_warehouse

	doc = get_mapped_doc("Collect Production Item", reference_name, {
		"Collect Production Item": {
		"doctype": "BOM",
			"field_map": {
				"item": "item",
				"item_name": "item_name",
				"uom": "uom",
				"quantity": "quantity",
				"collect_production_item": "name",
				"project": "project",
				"description": "description"
			},
		"validation": {
			"docstatus": ["=", 1]
		}
	},
		"Collect Production Item Materials": {
			"doctype": "BOM Item",
			"field_map": {
				"name": "collect_production_item_materials",
				"parent": "collect_production_item",
				"item_code": "item_code",
				"item_name": "item_name",
				"uom": "uom",
				"conversion_factor": "conversion_factor",
				"description": "description",
				"image": "image",
				"qty": "qty",
				"stock_qty": "stock_qty",
				"stock_uom": "stock_uom",
				"qty_consumed_per_unit": "qty_consumed_per_unit",
				"original_item": "original_item",
				"collect_production_item_materials": "name",
				"collect_production_item": "name",
			},
			"postprocess": update_item
		}
	}, target_doc)

	return doc	
	
	
