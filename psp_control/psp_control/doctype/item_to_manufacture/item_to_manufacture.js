// Copyright (c) 2019, Systematic-eg and contributors
// For license information, please see license.txt

frappe.provide("erpnext.item_to_manufacture");

frappe.ui.form.on('Item To Manufacture', {
	setup: function(frm) {
		// Set query for warehouses
		frm.set_query("source_warehouse", function() {
			return {
				filters: {
					'company': frm.doc.company,
					'is_group': 0
				}
			}
		});
		
		frm.set_query("wip_warehouse", function(doc) {
			return {
				filters: {
					'company': frm.doc.company,
					'is_group': 0
				}
			}
		});
		
		frm.set_query("reserve_warehouse", function(doc) {
			return {
				filters: {
					'company': frm.doc.company,
					'is_group': 0
				}
			}
		});

		frm.set_query("source_warehouse", "required_items", function() {
			return {
				filters: {
					'company': frm.doc.company,
					'is_group': 0
				}
			}
		});

		frm.set_query("sales_order", function() {
			return {
				filters: {
					"status": ["not in", ["Closed", "On Hold"]]
				}
			}
		});
		
		// Set query for FG Item
		frm.set_query("production_item", function() {
			return {
				query: "erpnext.controllers.queries.item_query",
				filters:[
					['is_stock_item', '=',1]
				]
			}
		});
		
		// Set query for FG Item
		frm.set_query("project", function() {
			return{
				filters:[
					['Project', 'status', 'not in', 'Completed, Cancelled']
				]
			}
		});
		
		frm.set_query("item_code", "required_items", function() {
			return {
				query: "erpnext.controllers.queries.item_query",
				filters: [["Item", "name", "!=", cur_frm.doc.production_item]]
			};
		});
	},
	onload_post_render: function(frm) {
		frm.get_field("required_items").grid.set_multiple_add("item_code", "required_qty");
	},
	onload: function(frm) {
		if (!frm.doc.status)
			frm.doc.status = 'Draft';

		frm.add_fetch("sales_order", "project", "project");

		if(frm.doc.__islocal) {
			erpnext.item_to_manufacture.set_default_warehouse(frm);
		}
	},
	refresh: function(frm) {
		frm.toggle_enable("production_item", frm.doc.__islocal);
		if (!frm.doc.__islocal && frm.doc.docstatus<2) {
			frm.add_custom_button(__("Update Cost"), function() {
				frm.events.update_cost(frm);
			});
		}
	},
	update_cost: function(frm) {
		return frappe.call({
			doc: frm.doc,
			method: "update_cost",
			freeze: true,
			args: {
				update_parent: true,
				save: false
			},
			callback: function(r) {
				refresh_field("items");
				if(!r.exc) frm.refresh_fields();
			}
		});
	}
});



erpnext.item_to_manufacture.ItemToManufactureController = erpnext.TransactionController.extend({
	conversion_rate: function(doc) {
		if(this.frm.doc.currency === this.get_company_currency()) {
			this.frm.set_value("conversion_rate", 1.0);
		} else {
			erpnext.item_to_manufacture.update_cost(doc);
		}
	},

	item_code: function(doc, cdt, cdn){
		var scrap_items = false;

		get_bom_material_detail(doc, cdt, cdn);
	},
	conversion_factor: function(doc, cdt, cdn) {
		if(frappe.meta.get_docfield(cdt, "stock_qty", cdn)) {
			var item = frappe.get_doc(cdt, cdn);
			frappe.model.round_floats_in(item, ["required_qty", "conversion_factor"]);
			item.stock_qty = flt(item.required_qty * item.conversion_factor, precision("stock_qty", item));
			refresh_field("stock_qty", item.name, item.parentfield);
			this.toggle_conversion_factor(item);
			this.frm.events.update_cost(this.frm);
		}
	},
});

$.extend(cur_frm.cscript, new erpnext.item_to_manufacture.ItemToManufactureController({frm: cur_frm}));


erpnext.item_to_manufacture.set_default_warehouse = function(frm) {
	if (!(frm.doc.source_warehouse || frm.doc.wip_warehouse || frm.doc.reserve_warehouse)) {
		frappe.call({
			method: "psp_control.psp_control.doctype.item_to_manufacture.item_to_manufacture.get_default_warehouse",
			callback: function(r) {
				if(!r.exe) {
					frm.set_value("source_warehouse", r.message.source_warehouse);
					frm.set_value("wip_warehouse", r.message.wip_warehouse);
					frm.set_value("reserve_warehouse", r.message.reserve_warehouse);
				}
			}
		});
	}
};

erpnext.item_to_manufacture.update_cost = function(doc) {
	calculate_rm_cost(doc);
	calculate_total(doc);
};

erpnext.item_to_manufacture.calculate_rm_cost = function(doc) {
	var rm = doc.required_items || [];
	var total_rm_cost = 0;
	var base_total_rm_cost = 0;
	for(var i=0;i<rm.length;i++) {
		var amount = flt(rm[i].rate) * flt(rm[i].required_qty);
		var base_amount = amount * flt(doc.conversion_rate);
		
		total_rm_cost += amount;
		base_total_rm_cost += base_amount;
	}
	cur_frm.set_value("raw_material_cost", total_rm_cost);
	cur_frm.set_value("base_raw_material_cost", base_total_rm_cost);
};

erpnext.item_to_manufacture.calculate_total = function(doc) {
	var total_cost = flt(doc.raw_material_cost);
	var base_total_cost = flt(doc.base_raw_material_cost);

	cur_frm.set_value("total_cost", total_cost);
	cur_frm.set_value("base_total_cost", base_total_cost);
};


var get_bom_material_detail= function(doc, cdt, cdn) {
	var d = locals[cdt][cdn];
	if (d.item_code) {
		return frappe.call({
			doc: doc,
			method: "get_bom_material_detail",
			args: {
				'item_code': d.item_code,
				'required_qty': d.required_qty,
				"stock_qty": d.stock_qty,
				"uom": d.uom,
				"stock_uom": d.stock_uom,
				"conversion_factor": d.conversion_factor
			},
			callback: function(r) {
				d = locals[cdt][cdn];
				$.extend(d, r.message);
				refresh_field("items");

				doc = locals[doc.doctype][doc.name];
				erpnext.item_to_manufacture.calculate_rm_cost(doc);
				erpnext.item_to_manufacture.calculate_total(doc);
			},
			freeze: true
		});
	}
};



cur_frm.cscript.required_qty = function(doc) {
	erpnext.item_to_manufacture.calculate_rm_cost(doc);
	erpnext.item_to_manufacture.calculate_total(doc);
};

cur_frm.cscript.rate = function(doc, cdt, cdn) {
	var d = locals[cdt][cdn];
	erpnext.item_to_manufacture.calculate_rm_cost(doc);
	erpnext.item_to_manufacture.calculate_total(doc);
};

erpnext.item_to_manufacture = {
	set_default_warehouse: function(frm) {
		if (!(frm.doc.source_warehouse || frm.doc.wip_warehouse || frm.doc.reserve_warehouse)) {
			frappe.call({
				method: "psp_control.psp_control.doctype.item_to_manufacture.item_to_manufacture.get_default_warehouse",
				callback: function(r) {
					if(!r.exe) {
						frm.set_value("source_warehouse", r.message.source_warehouse);
						frm.set_value("wip_warehouse", r.message.wip_warehouse)
						frm.set_value("reserve_warehouse", r.message.reserve_warehouse)
					}
				}
			});
		}
	},
	update_cost: function(doc) {
		calculate_rm_cost(doc);
		calculate_total(doc);
	},
	calculate_rm_cost: function(doc) {
		var rm = doc.required_items || [];
		var total_rm_cost = 0;
		var base_total_rm_cost = 0;
		for(var i=0;i<rm.length;i++) {
			var amount = flt(rm[i].rate) * flt(rm[i].required_qty);
			var base_amount = amount * flt(doc.conversion_rate);
			
			total_rm_cost += amount;
			base_total_rm_cost += base_amount;
		}
		cur_frm.set_value("raw_material_cost", total_rm_cost);
		cur_frm.set_value("base_raw_material_cost", base_total_rm_cost);
	},
	calculate_total: function(doc) {
		var total_cost = flt(doc.raw_material_cost);
		var base_total_cost = flt(doc.base_raw_material_cost);

		cur_frm.set_value("total_cost", total_cost);
		cur_frm.set_value("base_total_cost", base_total_cost);
	}
};

cur_frm.cscript.validate = function(doc) {
	erpnext.item_to_manufacture.update_cost(doc);
};

frappe.ui.form.on("Item To Manufacture Required", "required_qty", function(frm, cdt, cdn) {
	var d = locals[cdt][cdn];
	d.stock_qty = d.required_qty * d.conversion_factor;
	refresh_field("stock_qty", d.name, d.parentfield);
});

frappe.ui.form.on("Item To Manufacture Required", "items_remove", function(frm) {
	erpnext.item_to_manufacture.calculate_rm_cost(frm.doc);
	erpnext.item_to_manufacture.calculate_total(frm.doc);
});