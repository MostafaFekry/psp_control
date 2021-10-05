// Copyright (c) 2019, Systematic-eg and contributors
// For license information, please see license.txt


frappe.provide("erpnext.collect_production_item");

frappe.ui.form.on("Collect Production Item", {
	setup: function(frm) {

		frm.set_query("item", function() {
			return {
				query: "erpnext.controllers.queries.item_query",
				filters:[
					['is_stock_item', '=',1]
				]
			};
		});
		// Set query for warehouses
		frm.set_query("default_source_warehouse", function() {
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
		
		frm.set_query("sales_order", function() {
			return {
				filters: {
					"status": ["not in", ["Closed", "On Hold"]]
				}
			}
		});
		
		frm.set_query("project", function() {
			return{
				filters:[
					['Project', 'status', 'not in', 'Completed, Cancelled']
				]
			};
		});
		
		frm.set_query("item_code", "items", function() {
			return {
				query: "erpnext.controllers.queries.item_query",
				filters: [["Item", "name", "!=", cur_frm.doc.item]]
			};
		});
		
		frm.set_query("source_warehouse", "items", function() {
			return {
				filters: {
					'company': frm.doc.company
				}
			};
		});
		
		// formatter for material request item
		frm.set_indicator_formatter('item_code',
			function(doc) { return (doc.stock_qty<=doc.available_qty_at_source_warehouse) ? "green" : "orange" })
		

	},

	onload_post_render: function(frm) {
		frm.get_field("items").grid.set_multiple_add("item_code", "qty");
	},
	onload: function(frm) {
		if (!frm.doc.status)
			frm.doc.status = 'Draft';

		frm.add_fetch("sales_order", "project", "project");

		if(frm.doc.__islocal) {
			erpnext.collect_production_item.set_default_warehouse(frm);
		}

	},

	refresh: function(frm) {
		frm.toggle_enable("item", frm.doc.__islocal);
		
		frm.set_indicator_formatter('item_code',
			function(doc) {
				if (doc.original_item){
					return (doc.item_code != doc.original_item) ? "orange" : ""
				}
				return ""
			}
		)
		
		if (!frm.doc.__islocal && frm.doc.docstatus<2) {
			if(flt(frm.doc.per_reserved, 6) < 100 || flt(frm.doc.per_transferred) < 100) {
			    // Update Cost & Available Qty
			    frm.add_custom_button(__("Update Cost & Available Qty"), function() {
					frm.events.update_cost(frm);
				});
			}
		}
		
		if(frm.doc.docstatus==1) {
			
			if(frm.has_perm("submit")) {
				if(frm.doc.status === 'On Hold') {
				   // un-hold
				   frm.add_custom_button(__('Resume'), function() {
					   frm.events.update_status(frm,'Resume', 'Not Started')
				   }, __("Status"));

				   if(flt(frm.doc.per_reserved, 6) < 100 || flt(frm.doc.per_transferred) < 100) {
					   // close
					   frm.add_custom_button(__('Close'), () => frm.events.close_collect_production_item(), __("Status"));
				   }
				}
			   	else if(frm.doc.status === 'Closed') {
				   // un-close
				   frm.add_custom_button(__('Re-open'), function() {
					   frm.events.update_status(frm,'Re-open', 'Not Started')
				   }, __("Status"));
			   }
			}
		
			if(frm.doc.status !== 'To BOM' && frm.doc.status !== 'To Work Order' && frm.doc.status !== 'Completed' && frm.doc.status !== 'To Finish Good') {
				if(frm.doc.status !== 'On Hold') {
					
					frm.add_custom_button(__("Create Material Request"), function() {
						frappe.model.open_mapped_doc({
							method: "psp_control.psp_control.doctype.collect_production_item.collect_production_item.make_material_request",
							frm: frm
						});
					});
					
					frm.add_custom_button(__('Add or Reduce Material'), () => frm.events.add_new_material_item(frm), __("Update Materials"));
					frm.add_custom_button(__('Remove Material'), () => frm.events.delete_material_item(frm), __("Update Materials"));
					
								
					
					
					frm.add_custom_button(__('Send To Reserved'), () => frm.events.make_stock_entry_send_to_reserved(frm), __('Create Stock Entry'));
					frm.add_custom_button(__('Return From Reserved'), () => frm.events.make_stock_entry_return_from_reserved(frm), __('Create Stock Entry'));
					frm.add_custom_button(__('Send To WIP'), () => frm.events.make_stock_entry_send_to_wip(frm), __('Create Stock Entry'));
					frm.add_custom_button(__('Return From WIP'), () => frm.events.make_stock_entry_return_from_wip(frm), __('Create Stock Entry'));
					
					if (frm.has_perm("submit")) {
						if(flt(frm.doc.per_reserved, 6) < 100 || flt(frm.doc.per_transferred) < 100) {
							// hold
							frm.add_custom_button(__('Hold'), () => frm.events.hold_collect_production_item(frm), __("Status"));
							// close
							frm.add_custom_button(__('Close'), () => frm.events.hold_sales_order(frm), __("Status"));
						}
						if(flt(frm.doc.per_reserved, 6) == 100 && flt(frm.doc.per_transferred) == 100) {
							// hold
							frm.add_custom_button(__('Complete'), () => frm.events.complete_collect_production_item(frm), __("Status"));
							
						}
						
					}

				}
				frm.page.set_inner_btn_group_as_primary(__('Create Stock Entry'));
			}
			if(frm.doc.status == 'To BOM') {
				var bom_btn = frm.add_custom_button(__('Create Bom'), function() {
					frm.events.make_bom(frm);
				});
				bom_btn.addClass('btn-primary');
				frm.add_custom_button(__('Waiting for Approval'), () => frm.events.make_waiting_for_approval(frm), __("Status"));
			}
		}
		
		
	},
	hold_sales_order: function(frm) {
		// only message
		//frappe.msgprint(frm);
		frappe.msgprint(__('Document under update!'));
	},
	complete_collect_production_item: function(frm) {
		frm.events.update_status(frm,'Complete', 'To BOM');
	},
	make_stock_entry_send_to_reserved: function(frm) {
		frappe.model.open_mapped_doc({
			method: "psp_control.psp_control.doctype.collect_production_item.collect_production_item.make_stock_entry_send_to_reserved",
			frm: frm
		});
	},
	make_stock_entry_return_from_reserved: function(frm) {
		frappe.model.open_mapped_doc({
			method: "psp_control.psp_control.doctype.collect_production_item.collect_production_item.make_stock_entry_return_from_reserved",
			frm: frm
		});
	},
	make_stock_entry_send_to_wip: function(frm) {
		frappe.model.open_mapped_doc({
			method: "psp_control.psp_control.doctype.collect_production_item.collect_production_item.make_stock_entry_send_to_wip",
			frm: frm
		});
	},
	make_stock_entry_return_from_wip: function(frm) {
		frappe.model.open_mapped_doc({
			method: "psp_control.psp_control.doctype.collect_production_item.collect_production_item.make_stock_entry_return_from_wip",
			frm: frm
		});
	},
	make_bom: function(frm) {
		frappe.model.open_mapped_doc({
			method: "psp_control.psp_control.doctype.collect_production_item.collect_production_item.make_bom",
			frm: frm
		});
	},
	hold_collect_production_item: function(frm){
		var d = new frappe.ui.Dialog({
			title: __('Reason for Hold'),
			fields: [
				{
					"fieldname": "reason_for_hold",
					"fieldtype": "Text",
					"reqd": 1,
				}
			],
			primary_action: function() {
				var data = d.get_values();
				frappe.call({
					method: "frappe.desk.form.utils.add_comment",
					args: {
						reference_doctype: frm.doctype,
						reference_name: frm.docname,
						content: __('Reason for hold: ')+data.reason_for_hold,
						comment_email: frappe.session.user
					},
					callback: function(r) {
						if(!r.exc) {
							frm.events.update_status(frm,'Hold', 'On Hold');
							d.hide();
						}
					}
				});
			}
		});
		d.show();
	},
	make_waiting_for_approval: function(frm){
		var d = new frappe.ui.Dialog({
			title: __('Reason for back to (Waiting for Approval)'),
			fields: [
				{
					"fieldname": "reason_for_hold",
					"fieldtype": "Text",
					"reqd": 1,
				}
			],
			primary_action: function() {
				var data = d.get_values();
				frappe.call({
					method: "frappe.desk.form.utils.add_comment",
					args: {
						reference_doctype: frm.doctype,
						reference_name: frm.docname,
						content: __('Reason for back to (Waiting for Approval): ')+data.reason_for_hold,
						comment_email: frappe.session.user
					},
					callback: function(r) {
						if(!r.exc) {
							frm.events.update_status(frm,'To BOM', 'Waiting for Approval');
							d.hide();
						}
					}
				});
			}
		});
		d.show();
	},
	update_status: function(frm,label, status){
		frappe.ui.form.is_saving = true;
		frappe.call({
			method: "psp_control.psp_control.doctype.collect_production_item.collect_production_item.update_status",
			args: {status: status, name: frm.doc.name},
			callback: function(r){
				if(r.message) {
					frm.set_value("status", r.message);
					frm.reload_doc();
				}
			},
			always: function() {
				frappe.ui.form.is_saving = false;
			}
		});
	},
	update_cost: function(frm) {
		return frappe.call({
			doc: frm.doc,
			method: "update_cost",
			freeze: true,
			args: {
				update_parent: true,
				from_child_bom:false,
				save: false
			},
			callback: function(r) {
				refresh_field("items");
				if(!r.exc) frm.refresh_fields();
			}
		});
	},
	add_new_material_item: function(frm) {
		const cannot_add_row = false;
		const child_docname = "items";

		this.data = [];
		const fields = [{
			fieldtype:'Link',
			fieldname:"item_code",
			options: 'Item',
			in_list_view: 1,
			read_only: 0,
			disabled: 0,
			label: __('Item Code')
		}, {
			fieldtype:'Float',
			fieldname:"qty",
			default: 0,
			read_only: 0,
			in_list_view: 1,
			label: __('Qty')
		}];


		const dialog = new frappe.ui.Dialog({
			title: __("Add or Reduce Items Materials"),
			fields: [
				{
					fieldname: "trans_items",
					fieldtype: "Table",
					label: "Items",
					description: __('Allow to reduce quantity by set as (-1)'),
					cannot_add_rows: cannot_add_row,
					in_place_edit: true,
					reqd: 1,
					data: this.data,
					get_data: () => {
						return this.data;
					},
					fields: fields
				},
			],

			primary_action: function() {
				var trans_items = this.get_values()["trans_items"];
				frm.call({
					method: 'psp_control.psp_control.doctype.collect_production_item.collect_production_item.make_add_new_material',
					args: {
						'trans_items': trans_items,
						'reference_name': frm.docname
					},
					freeze: true,
					callback: function() {
						frm.reload_doc();
					}
				});
				this.hide();
				refresh_field("items");
			},
			primary_action_label: __('Submit')
		});

		dialog.show();
	},
	delete_material_item: function(frm) {
		var d = new frappe.ui.Dialog({
			title: __('Remove Item From Materials Items'),
			fields: [
				{
					fieldname: "remove_item_s_b",
					fieldtype: "Section Break",
					label: __('Selet Item')
				},
				{
					fieldtype:'Link',
					fieldname:'item_code',
					label: __('Item Code'),
					options: 'Item',
					reqd: 1,
					get_query: function (doc) {
						return { filters: [["Item", "name", "!=", cur_frm.doc.item]] };
					}
				},
				{
					fieldname: "reason_for_delete",
					label: __('Comment Reason For Delete'),
					fieldtype: "Small Text",
					reqd: 1,
				}
			],
			primary_action: function() {
				var data = d.get_values();
				frappe.call({
					method: "psp_control.psp_control.doctype.collect_production_item.collect_production_item.make_remove_item_material",
					args: {
						reference_doctype: frm.doctype,
						reference_name: frm.docname,
						delet_item_code: data.item_code,
						content: __('Reason for delete (')+data.item_code+('): ')+data.reason_for_delete,
						comment_email: frappe.session.user
					},
					callback: function(r) {
						if(!r.exc) {
							frappe.msgprint(__('Document updated successfully, Item removed..'))
							frm.reload_doc();
							refresh_field("items");
							d.hide();
						}
					}
				});
			}
		});
		d.show();
	}
});

erpnext.collect_production_item.CollectProductionItemController = erpnext.TransactionController.extend({
	conversion_rate: function(doc) {
		if(this.frm.doc.currency === this.get_company_currency()) {
			this.frm.set_value("conversion_rate", 1.0);
		} else {
			erpnext.collect_production_item.update_cost(doc);
		}
	},

	item_code: function(doc, cdt, cdn){
		var scrap_items = false;
		get_bom_material_detail(doc, cdt, cdn, scrap_items);
	},
	conversion_factor: function(doc, cdt, cdn) {
		if(frappe.meta.get_docfield(cdt, "stock_qty", cdn)) {
			var item = frappe.get_doc(cdt, cdn);
			frappe.model.round_floats_in(item, ["qty", "conversion_factor"]);
			item.stock_qty = flt(item.qty * item.conversion_factor, precision("stock_qty", item));
			refresh_field("stock_qty", item.name, item.parentfield);
			this.toggle_conversion_factor(item);
			this.frm.events.update_cost(this.frm);
		}
	},
});

$.extend(cur_frm.cscript, new erpnext.collect_production_item.CollectProductionItemController({frm: cur_frm}));

erpnext.collect_production_item.set_default_warehouse = function(frm) {
	if (!(frm.doc.default_source_warehouse || frm.doc.wip_warehouse || frm.doc.reserve_warehouse)) {
		frappe.call({
			method: "psp_control.psp_control.doctype.collect_production_item.collect_production_item.get_default_warehouse",
			callback: function(r) {
				if(!r.exe) {
					frm.set_value("default_source_warehouse", r.message.default_source_warehouse);
					frm.set_value("wip_warehouse", r.message.wip_warehouse);
					frm.set_value("reserve_warehouse", r.message.reserve_warehouse);
				}
			}
		});
	}
};

var get_bom_material_detail= function(doc, cdt, cdn, scrap_items) {
	var d = locals[cdt][cdn];
	if (d.item_code) {
		return frappe.call({
			doc: doc,
			method: "get_bom_material_detail",
			args: {
				'item_code': d.item_code,
				'qty': d.qty,
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
				erpnext.collect_production_item.calculate_rm_cost(doc);
				erpnext.collect_production_item.calculate_total(doc);
			},
			freeze: true
		});
	}
};

erpnext.collect_production_item.update_cost = function(doc) {
	erpnext.collect_production_item.calculate_rm_cost(doc);
	erpnext.collect_production_item.calculate_total(doc);
};

// rm : raw material
erpnext.collect_production_item.calculate_rm_cost = function(doc) {
	var rm = doc.items || [];
	var total_rm_cost = 0;
	var base_total_rm_cost = 0;
	for(var i=0;i<rm.length;i++) {
		var amount = flt(rm[i].rate) * flt(rm[i].qty);
		var base_amount = amount * flt(doc.conversion_rate);

		frappe.model.set_value('Collect Production Item Materials', rm[i].name, 'base_rate',
			flt(rm[i].rate) * flt(doc.conversion_rate));
		frappe.model.set_value('Collect Production Item Materials', rm[i].name, 'amount', amount);
		frappe.model.set_value('Collect Production Item Materials', rm[i].name, 'base_amount', base_amount);
		frappe.model.set_value('Collect Production Item Materials', rm[i].name,
			'qty_consumed_per_unit', flt(rm[i].stock_qty)/flt(doc.quantity));

		total_rm_cost += amount;
		base_total_rm_cost += base_amount;
	}
	cur_frm.set_value("raw_material_cost", total_rm_cost);
	cur_frm.set_value("base_raw_material_cost", base_total_rm_cost);
};

// Calculate Total Cost
erpnext.collect_production_item.calculate_total = function(doc) {
	var total_cost = flt(doc.raw_material_cost)
	var base_total_cost = flt(doc.base_raw_material_cost)

	cur_frm.set_value("total_cost", total_cost);
	cur_frm.set_value("base_total_cost", base_total_cost);
};

cur_frm.cscript.validate = function(doc) {
	erpnext.collect_production_item.update_cost(doc);
};

cur_frm.cscript.qty = function(doc) {
	erpnext.collect_production_item.calculate_rm_cost(doc);
	erpnext.collect_production_item.calculate_total(doc);
};

cur_frm.cscript.rate = function(doc, cdt, cdn) {
	var d = locals[cdt][cdn];
	erpnext.collect_production_item.calculate_rm_cost(doc);
	erpnext.collect_production_item.calculate_total(doc);
};

frappe.ui.form.on("Collect Production Item Materials", "qty", function(frm, cdt, cdn) {
	var d = locals[cdt][cdn];
	d.stock_qty = d.qty * d.conversion_factor;
	refresh_field("stock_qty", d.name, d.parentfield);
});

frappe.ui.form.on("Collect Production Item Materials", "items_remove", function(frm) {
	erpnext.collect_production_item.calculate_rm_cost(frm.doc);
	erpnext.collect_production_item.calculate_total(frm.doc);
});

frappe.ui.form.on("Collect Production Item Materials", "item_code", function(frm, cdt, cdn) {
	var row = locals[cdt][cdn];
	if(!row.item_code) {
		frappe.throw(__("Please set the Item Code first"));
	} else if(frm.doc.default_source_warehouse) {
		frappe.call({
			"method": "erpnext.stock.utils.get_latest_stock_qty",
			args: {
				item_code: row.item_code,
				warehouse: frm.doc.default_source_warehouse
			},
			callback: function (r) {
				frappe.model.set_value(row.doctype, row.name,
					"available_qty_at_source_warehouse", r.message);
			}
		})
	}
});


