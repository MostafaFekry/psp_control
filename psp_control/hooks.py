# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from . import __version__ as app_version

app_name = "psp_control"
app_title = "PSP Control"
app_publisher = "MostafaFekry"
app_description = "Control item manufacture and tender"
app_icon = "octicon octicon octicon-tools"
app_color = "grey"
app_email = "mostafa.fekry@gmail.com"
app_license = "MIT"

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/psp_control/css/psp_control.css"
# app_include_js = "/assets/psp_control/js/psp_control.js"

# include js, css files in header of web template
# web_include_css = "/assets/psp_control/css/psp_control.css"
# web_include_js = "/assets/psp_control/js/psp_control.js"

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
#	"Role": "home_page"
# }

# Website user home page (by function)
# get_website_user_home_page = "psp_control.utils.get_home_page"

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Installation
# ------------

# before_install = "psp_control.install.before_install"
# after_install = "psp_control.install.after_install"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "psp_control.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
#	}
# }

doc_events = {
    "Stock Entry": {
        "on_submit": "psp_control.api.stock_entry_on_submit",
        "before_submit": "psp_control.api.stock_entry_before_submit",
        "on_cancel": "psp_control.api.stock_entry_on_cancel"
    },
	"BOM": {
        "on_submit": "psp_control.api.bom_on_submit"
    },
	"Work Order": {
        "on_submit": "psp_control.api.work_order_on_submit"
    }
}

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"psp_control.tasks.all"
# 	],
# 	"daily": [
# 		"psp_control.tasks.daily"
# 	],
# 	"hourly": [
# 		"psp_control.tasks.hourly"
# 	],
# 	"weekly": [
# 		"psp_control.tasks.weekly"
# 	]
# 	"monthly": [
# 		"psp_control.tasks.monthly"
# 	]
# }

# Testing
# -------

# before_tests = "psp_control.install.before_tests"

# Overriding Whitelisted Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "psp_control.event.get_events"
# }

fixtures = [{"dt": "Custom Script", "filters": [["name", "in", [
		"Stock Entry-Client",
		"Work Order-Client"
	]]]},
    {"dt": "Custom Field", "filters": [["name", "like", 
        "%collect_production_item"
    ]]}
]