# -*- coding: utf-8 -*-
# Copyright (c) 2019, Systematic-eg and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe, erpnext

from frappe.utils import cint, cstr, flt
from frappe import _
from erpnext.setup.utils import get_exchange_rate
from frappe.model.document import Document	
from erpnext.stock.doctype.item.item import validate_end_of_life

from erpnext.stock.utils import get_bin, validate_warehouse_company, get_latest_stock_qty


from erpnext.utilities.transaction_base import validate_uom_is_integer
import functools
from six import string_types
class ItemToManufacture(Document):
	
	def validate(self):
		self.validate_production_item()
		self.validate_sales_order()
		self.set_default_warehouse()
		self.validate_warehouse_belongs_to_company()
		self.validate_qty()
		self.set_conversion_rate()		
		self.validate_uom_is_interger()
		self.set_bom_material_details()
		self.validate_materials()
		self.calculate_cost()
		self.status = self.get_status()

		validate_uom_is_integer(self, "stock_uom", ["qty", "produced_qty"])
		
		
	def validate_sales_order(self):
		if self.sales_order:
			so = frappe.db.sql("""
				select so.name, so_item.delivery_date, so.project
				from `tabSales Order` so
				inner join `tabSales Order Item` so_item on so_item.parent = so.name
				left join `tabProduct Bundle Item` pk_item on so_item.item_code = pk_item.parent
				where so.name=%s and so.docstatus = 1 and (
					so_item.item_code=%s or
					pk_item.item_code=%s )
			""", (self.sales_order, self.production_item, self.production_item), as_dict=1)

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
				""", (self.sales_order, self.production_item), as_dict=1)

			if len(so):
				if not self.expected_delivery_date:
					self.expected_delivery_date = so[0].delivery_date

				if so[0].project:
					self.project = so[0].project

			else:
				frappe.throw(_("Sales Order {0} is not valid").format(self.sales_order))
		
	def validate_production_item(self):
		if frappe.db.get_value("Item", self.production_item, "has_variants"):
			frappe.throw(_("Production Order cannot be raised against a Item Template"), ItemHasVariantError)
		else:
			ret = frappe.db.get_value("Item", self.production_item, ["description", "stock_uom", "item_name"])
			self.description = ret[0]
			self.uom = ret[1]
			self.item_name= ret[2]

		if self.production_item:
			validate_end_of_life(self.production_item)
		
	def set_default_warehouse(self):
		if not self.source_warehouse:
			self.source_warehouse = frappe.db.get_single_value("PSP Settings", "default_source_warehouse")
		if not self.wip_warehouse:
			self.wip_warehouse = frappe.db.get_single_value("Manufacturing Settings", "default_wip_warehouse")
		if not self.reserve_warehouse:
			self.reserve_warehouse = frappe.db.get_single_value("PSP Settings", "default_reserve_warehouse")

	def validate_warehouse_belongs_to_company(self):
		warehouses = [self.reserve_warehouse, self.wip_warehouse]
		for d in self.get("required_items"):
			if d.source_warehouse not in warehouses:
				warehouses.append(d.source_warehouse)

		for wh in warehouses:
			validate_warehouse_company(wh, self.company)
	
	def validate_qty(self):
		if not self.qty > 0:
			frappe.throw(_("Quantity to Manufacture must be greater than 0."))
	
	def update_status(self, status=None):
		'''Update status of production order if unknown'''
		if status != "Stopped":
			status = self.get_status(status)

		if status != self.status:
			self.db_set("status", status)

		self.update_required_items()

		return status

	def get_status(self, status=None):
		'''Return the status based on stock entries against this production order'''
		if not status:
			status = self.status

		if self.docstatus==0:
			status = 'Draft'
		elif self.docstatus==1:
			if status != 'Stopped':
				stock_entries = frappe._dict(frappe.db.sql("""select purpose, sum(fg_completed_qty)
					from `tabStock Entry` where production_order=%s and docstatus=1
					group by purpose""", self.name))

				status = "Not Started"
				if stock_entries:
					status = "In Process"
					produced_qty = stock_entries.get("Manufacture")
					if flt(produced_qty) == flt(self.qty):
						status = "Completed"
		else:
			status = 'Cancelled'

		return status
		
	def update_cost(self, update_parent=True, save=True):
		if self.docstatus == 2:
			return

		existing_bom_cost = self.total_cost

		for d in self.get("required_items"):
			rate = self.get_rm_rate({
				"item_code": d.item_code,
				"required_qty": d.required_qty,
				"uom": d.uom,
				"stock_uom": d.stock_uom,
				"conversion_factor": d.conversion_factor
			})
			if rate:
				d.rate = rate
			d.amount = flt(d.rate) * flt(d.required_qty)

		if self.docstatus == 1:
			self.flags.ignore_validate_update_after_submit = True
			self.calculate_cost()
		if save:
			self.save()

		frappe.msgprint(_("Cost Updated"))

	def calculate_cost(self):
		"""Calculate bom totals"""
		self.calculate_rm_cost()
		self.total_cost = self.raw_material_cost
		self.base_total_cost = self.base_raw_material_cost
		
	def calculate_rm_cost(self):
		"""Fetch RM rate as per today's valuation rate and calculate totals"""
		total_rm_cost = 0
		base_total_rm_cost = 0

		for d in self.get('required_items'):
			d.base_rate = flt(d.rate) * flt(self.conversion_rate)
			d.amount = flt(d.rate, d.precision("rate")) * flt(d.required_qty, d.precision("required_qty"))
			d.base_amount = d.amount * flt(self.conversion_rate)

			total_rm_cost += d.amount
			base_total_rm_cost += d.base_amount
		self.raw_material_cost = total_rm_cost
		self.base_raw_material_cost = base_total_rm_cost
	
	def company_currency(self):
		return erpnext.get_company_currency(self.company)
	
	def set_conversion_rate(self):
		if self.currency == self.company_currency():
			self.conversion_rate = 1
		elif self.conversion_rate == 1 or flt(self.conversion_rate) <= 0:
			self.conversion_rate = get_exchange_rate(self.currency, self.company_currency(), args="for_buying")
	
	def validate_uom_is_interger(self):
		from erpnext.utilities.transaction_base import validate_uom_is_integer
		validate_uom_is_integer(self, "uom", "required_qty", "BOM Item")
		validate_uom_is_integer(self, "stock_uom", "stock_qty", "BOM Item")
	
	def validate_rm_item(self, item):
		if (item[0]['name'] in [it.item_code for it in self.required_items]) and item[0]['name'] == self.production_item:
			frappe.throw(_("BOM #{0}: Raw material cannot be same as Item to Manufacture").format(self.name))
			
	def get_item_det(self, item_code):
		item = frappe.db.sql("""select name, item_name, docstatus, description, image,
			is_sub_contracted_item, stock_uom, default_bom, last_purchase_rate, include_item_in_manufacturing
			from `tabItem` where name=%s""", item_code, as_dict = 1)

		if not item:
			frappe.throw(_("Item: {0} does not exist in the system").format(item_code))

		return item
		
	def set_bom_material_details(self):
		for item in self.get("required_items"):

			ret = self.get_bom_material_detail({
				"item_code": item.item_code,
				"item_name": item.item_name,
				"stock_qty": item.stock_qty,
				"required_qty": item.required_qty,
				"uom": item.uom,
				"stock_uom": item.stock_uom,
				"conversion_factor": item.conversion_factor
			})
			for r in ret:
				if not item.get(r):
					item.set(r, ret[r])

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
			 'description'  : item and args['description'] or '',
			 'image'		: item and args['image'] or '',
			 'stock_uom'	: item and args['stock_uom'] or '',
			 'uom'			: item and args['stock_uom'] or '',
 			 'conversion_factor': 1,
			 'rate'			: rate,
			 'required_qty'	: args.get("required_qty") or args.get("stock_qty") or 1,
			 'stock_qty'	: args.get("required_qty") or args.get("stock_qty") or 1,
			 'base_rate'	: rate
		}

		return ret_item
	
	def get_rm_rate(self, arg):
		"""	Get raw material rate as per selected method, if bom exists takes bom cost """
		rate = 0
		if not self.rm_cost_as_per:
			self.rm_cost_as_per = "Valuation Rate"

		if arg:
			#Customer Provided parts will have zero rate
			if not frappe.db.get_value('Item', arg["item_code"], 'is_customer_provided_item'):
				rate = self.get_valuation_rate(arg) * (arg.get("conversion_factor") or 1)

				if not rate:
					frappe.msgprint(_("{0} not found for item {1}")
						.format(self.rm_cost_as_per, arg["item_code"]), alert=True)

		return flt(rate) / (self.conversion_rate or 1)
	
	def validate_materials(self):
		""" Validate raw material entries """

		def get_duplicates(lst):
			seen = set()
			seen_add = seen.add
			for item in lst:
				if item.item_code in seen or seen_add(item.item_code):
					yield item

		if not self.get('required_items'):
			frappe.throw(_("Raw Materials cannot be blank."))
		check_list = []
		for m in self.get('required_items'):
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

	
@frappe.whitelist()
def get_default_warehouse():
	source_warehouse = frappe.db.get_single_value("PSP Settings",
		"default_source_warehouse")
	wip_warehouse = frappe.db.get_single_value("Manufacturing Settings",
		"default_wip_warehouse")
	reserve_warehouse = frappe.db.get_single_value("PSP Settings",
		"default_reserve_warehouse")
	return {"source_warehouse": source_warehouse, "wip_warehouse": wip_warehouse, "reserve_warehouse": reserve_warehouse}