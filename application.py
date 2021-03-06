
import requests, os
from datetime import datetime
from pprint import pprint
from flask import Flask, request
from flask_restful import Resource, Api
# from flask.ext.jsonpify import jsonify
from flask_jsonpify import jsonify
from threading import Lock
from collections import deque
from timeit import default_timer as timer

class MessageStorage (object):
	def __init__(self):
		self.lock = Lock()
		self.storage = dict()

	def push_message(self, id, data):
		self.lock.acquire()
		msgs = self.storage.get(id)
		if not msgs:
			msgs = deque()
			msgs.append(data)
			self.storage[id] = msgs
		else:
			msgs.append(data)
		self.lock.release()

	def pop_message(self, id):
		self.lock.acquire()
		try:
			msgs = self.storage.get(id)
			if msgs: 
				msg = msgs.popleft()
				self.lock.release()
				return msg
			else:
				self.lock.release()
				return None
		except IndexError:
			self.lock.release()
			return None

class NexmoWhatsAppConnection (object):

	message_storage = MessageStorage()

	def __init__(self):
		self.sandbox_url = 'https://sandbox.nexmodemo.com/v0.1/messages/'
		self.auth_token = os.environ.get('NEXMO_WHATSAPP_AUTH_TOKEN')
		self.my_phone = os.environ.get('NEXMO_WHATSAPP_PHONE')

		if not self.auth_token: raise Exception('Need NEXMO_WHATSAPP_AUTH_TOKEN environment variable')
		if not self.my_phone: raise Exception('Need NEXMO_WHATSAPP_PHONE environment variable')

	def mtm_required(self, caller_id):
		con = SFConnection()
		con.authenticate()
		contact_response = con.get_contact_for_phone(caller_id)

		# pprint(contact_response)

		if not contact_response: raise Exception('No contact found')
		contact = contact_response['records'][0]
		return contact['Whatsapp_MTM_required__c']

	def send_message(self, to_phone, message):
		print('In NexmoWhatsAppConnection.send_message with phone %s', to_phone)
		if self.mtm_required(to_phone):
			app.logger.info('MTM required for %s', to_phone)
			self.send_mtm_message(to_phone, message)
		else:
			app.logger.info('MTM not required for %s', to_phone)
			self.send_message_no_mtm_check(to_phone, message)

	def send_message_no_mtm_check(self, to_phone, message):
		msg = {
			"from": {
      			"type": "whatsapp",
      			"number":self.my_phone
   			},
   			"to":{
      			"type":"whatsapp",
      			"number":to_phone
   			},
   			"message":{
      			"content":{
         			"type":"text",
         			"text": message
      			}
   			}
   		}
		
		# pprint(msg)

		r = requests.post(self.sandbox_url, 
   			headers={'Content-Type': 'application/json', 
   				'Accept': 'application/json',
   				'Authorization': 'Bearer ' + self.auth_token},
   			json=msg)

		if r.status_code != requests.codes.ok:
			r.raise_for_status()

	def send_mtm_message(self, to_phone, message):
		msg = {
   			"to":{
      			"type":"whatsapp",
      			"number": to_phone
   			},
   			"from":{
      			"type":"whatsapp",
      			"number":self.my_phone
   			},
   			"message":{
      			"content":{
         			"type":"template",
         			"template":{
            			"name":"whatsapp:hsm:technology:nexmo:simplewelcome",
            			"parameters":[{
                  			"default":"Nexmo"
               			},
               			{
                    		"default":"interact with us over whatsapp"
               			}]
         			}
      			},
      			"whatsapp":{
         			"policy":"deterministic",
         			"locale":"en"
      			}
   			}
		}

		r = requests.post(self.sandbox_url, 
   			headers={'Content-Type': 'application/json', 
   				'Accept': 'application/json',
   				'Authorization': 'Bearer ' + self.auth_token},
   			json=msg)

		if r.status_code != requests.codes.ok:
			r.raise_for_status()

		app.logger.debug('Push to global message storage: %s', to_phone)
		NexmoWhatsAppConnection.message_storage.push_message(to_phone, {'to': to_phone, 'message': message})

		# Ugly, should not be here.
		con = SFConnection()
		con.authenticate()
		con.update_whatsapp_mtm_date(to_phone)

	def receive_answer(self, req):
		app.logger.debug('In receive_answer')
		print('In receive_answer for whatsapp')

		# pprint(req)

		# If we receive an answer from a client, we check if there are any pending messages.
		from_phone = req['from']['number']

		# Ugly while loop. Better use iterator.

		while True:
			msg = NexmoWhatsAppConnection.message_storage.pop_message(from_phone)

			if not msg: 
				break
			
			app.logger.info('Sending pending message for %s', from_phone)
			pprint(msg)
			self.send_message_no_mtm_check(msg['to'], msg['message'])

	def receive_status(self, req):
		app.logger.debug('in receive_status')
		print('In receive status for whatsapp')
		# pprint(req)

		"""
		if req['status'] == 'delivered':
			print('Got delivered')

			msg = global_message_storage.get_message(req['message_uuid'])
			if msg:
				print('Found stored message')
				pprint(msg)
				global_message_storage.del_message(req['message_uuid'])

				self.send_message_no_mtm_check(msg['to'], msg['message'])
		"""

class NexmoWhatsAppSendMessageOrder (Resource):

	def post(self):
		timer_start = timer()
		# app.logger.debug('In NexmoWhatsAppSendMessageOrder.post')
		print('In NexmoWhatsAppSendMessageOrder.post')
		pprint(request.get_json())
		req = OverAiRequest(request.get_json())
		nexmo_con = NexmoWhatsAppConnection()
		nexmo_con.send_message(
			req.get_parameter('WHATSAPP_RECIPIENT'), 
			req.get_parameter('WHATSAPP_MSG'))
		timer_end = timer()
		print('NexmoWhatsAppSendMessageOrder took ', timer_end-timer_start, ' secs')
		return jsonify({"ForceIntent": {"IntentName": "end_call"}})
		# return jsonify({'Result': {'IntroSpeakOut': 'Ok, the Whatsapp message is on its way to you.'}})

class NexmoWhatsAppSendMessageProduct (Resource):

	messages = {
		'en-US': { 
			'conversation analyzer': """Thank you very much for your interest in Conversation Analyzer. If you'd like to learn more please visit https://www.newvoicemedia.com/en-us/resources/conversation-analyzer""",
			'smart numbers': """We're happy you'd like to know more about our Smart Numbers capability. Please check out https://www.vonage.com/business/perspectives/vonage-number-programmability-leap-forward-business-communication/ to learn more.""",
			'single pane of glass': """Thank you very much for calling us regarding our Single Pane of Glass offering. Please consult https://www.vonage.com/business/unified-communications/business-phone-system-features/?icmp=BMM_D_products_unifiedcommunic_businessphonesy to learn more about it."""
		},
		'de-DE': {
			'conversation analyzer': """Danke für ihr Interesse an unserem Conversation Analyzer. Wenn sie mehr wissen möchten bitte besuchen sie unsere Produktseite unter https://www.newvoicemedia.com/en-us/resources/conversation-analyzer""",
			'smart numbers': """ Wir freuen uns, dass sie mehr über Smart Numbers lernen möchten. Bitte schauen sie auf https://www.vonage.com/business/perspectives/vonage-number-programmability-leap-forward-business-communication/ um mehr zu erfahren""",
			'single pane of glass': """Danke für ihren Anruf im Hinblick auf unser Single Pane of Glass Angebot. Bitte besuchen sie https://www.vonage.com/business/unified-communications/business-phone-system-features/?icmp=BMM_D_products_unifiedcommunic_businessphonesy um mehr über dieses Produkt zu lernen.""",
			'single pain of glass': """Danke für ihren Anruf im Hinblick auf unser Single Pane of Glass Angebot. Bitte besuchen sie https://www.vonage.com/business/unified-communications/business-phone-system-features/?icmp=BMM_D_products_unifiedcommunic_businessphonesy um mehr über dieses Produkt zu lernen."""
		}
	}

	def post(self):
		app.logger.debug('In NexmoWhatsAppSendMessageProduct.post')
		pprint(request.get_json())
		req = OverAiRequest(request.get_json())
		product = req.get_parameter('PRODUCT').lower()
		language = req.get_language()

		print('Trying to find message text for ', product, ' in language ', language)

		try: 
			whatsapp_message = self.messages[language][product]
			print('Found message text')
		except KeyError:
			print('No message text found')
			whatsapp_message = 'Error, no such product or language found'

		nexmo_con = NexmoWhatsAppConnection()
		nexmo_con.send_message(
			req.get_parameter('WHATSAPP_RECIPIENT'), 
			whatsapp_message)
		return jsonify({"ForceIntent": {"IntentName": "product_confirm_route"}})
		# return jsonify({'Result': {'IntroSpeakOut': 'Ok, the Whatsapp message is on its way to you.'}})

class NexmoWhatsAppReceiveMessage (Resource):
	def post(self):
		req = request.get_json()
		nexmo_con = NexmoWhatsAppConnection()
		nexmo_con.receive_answer(req)

class NexmoWhatsAppReceiveStatus (Resource):
	def post(self):
		req = request.get_json()
		nexmo_con = NexmoWhatsAppConnection()
		nexmo_con.receive_status(req)

class SFConnection (object):

	auth_url = 'https://login.salesforce.com/services/oauth2/token'
	api_version = 'v37.0'

	def __init__(self):
		self.auth_data = None

		self.org_url = os.environ.get('SF_ORG_URL') 
		if not self.org_url: raise Exception('Need Salesforce Org URL')
		self.username = os.environ.get('SF_USERNAME') 
		if not self.username: raise Exception('Need Salesforce Username')
		self.password = os.environ.get('SF_PASSWORD') 
		if not self.password: raise Exception('Need Salesforce Password')
		self.security_token = os.environ.get('SF_SECURITY_TOKEN')
		if not self.security_token: raise Exception('Need Salesforce Security Token')
		self.client_id = os.environ.get('SF_CLIENT_ID')
		if not self.client_id: raise Exception('Need Salesforce Client ID')
		self.client_secret = os.environ.get('SF_CLIENT_SECRET')
		if not self.client_secret: raise Exception('Need Salesforce Client Secret')

		self.rest_url = self.org_url + 'services/data/' + self.api_version

	def authenticate (self):
		r = requests.post(self.auth_url, data = {'grant_type': 'password',
			'client_id': self.client_id,
			'client_secret': self.client_secret,
			'username': self.username,
			'password': self.password + self.security_token})

		if r.status_code != requests.codes.ok:
			r.raise_for_status()

		self.auth_data = r.json()

	def get_access_token(self):
		return self.auth_data['access_token']

	def get_last_order_by_phone (self, phone):
		query = """select order__c.name, 
			contact__r.name, 
			contact__r.id,
			order__c.status__c, 
			order__c.delivery_date__c
			from order__c 
			where contact__r.phone like '%%%s' 
				or contact__r.homephone = '%%%s'
				or contact__r.mobilephone = '%%%s'
			order by order__c.CreatedDate desc 
			limit 1""" % (phone, phone, phone)

		headers = {'Authorization': 'Bearer ' + self.get_access_token()}

		params = {'q': query}
		r = requests.get(self.rest_url + '/query/', headers=headers, params=params)

		if r.status_code != requests.codes.ok:
			r.raise_for_status()

		return r.json()

	def get_order_by_number(self, phone, order_number):

		query = """select order__c.name, 
			contact__r.name, 
			contact__r.id,
			order__c.status__c, 
			order__c.delivery_date__c
			from order__c 
			where (contact__r.phone like '%%%s' 
				or contact__r.homephone = '%%%s'
				or contact__r.mobilephone = '%%%s')
				and order__c.name like '%%%s'
			order by order__c.CreatedDate desc 
			limit 1""" % (phone, phone, phone, order_number)

		headers = {'Authorization': 'Bearer ' + self.get_access_token()}

		params = {'q': query}
		r = requests.get(self.rest_url + '/query/', headers=headers, params=params)

		if r.status_code != requests.codes.ok:
			r.raise_for_status()

		return r.json()

	def update_contact_for_order(self, contact_id, order_number):
		headers = {'Authorization': 'Bearer ' + self.get_access_token(),
			'Content-Type': 'application/json'}
		r = requests.patch(self.rest_url + '/sobjects/Contact/' + contact_id, 
			headers=headers,
			json={'Order_Pop__c': order_number})
		if r.status_code != requests.codes.ok:
			r.raise_for_status()

	def update_contact_for_ai_context(self, contact_id, ai_context):
		headers = {'Authorization': 'Bearer ' + self.get_access_token(),
			'Content-Type': 'application/json'}
		r = requests.patch(self.rest_url + '/sobjects/Contact/' + contact_id, 
			headers=headers,
			json={'Vonage_AI_Context__c': ai_context})
		if r.status_code != requests.codes.ok:
			r.raise_for_status()

	def get_contact_for_phone(self, phone):
		query = """select  
			id,
			Name,
			FirstName,
			LastName,
			OtherPhone,
			Last_Whatsapp_MTM__c,
			Whatsapp_MTM_required__c,
			Outstanding_Amount__c,
			Currency_Text_To_Speech__c
			from contact
			where (phone like '%%%s' 
				or homephone = '%%%s'
				or mobilephone = '%%%s')
			order by CreatedDate desc 
			limit 1""" % (phone, phone, phone)

		headers = {'Authorization': 'Bearer ' + self.get_access_token()}

		params = {'q': query}
		r = requests.get(self.rest_url + '/query/', headers=headers, params=params)

		if r.status_code != requests.codes.ok:
			r.raise_for_status()

		return r.json()

	def update_whatsapp_mtm_date(self, contact_phone, mtm_date = None):
		if not mtm_date:
			mtm_date = datetime.utcnow()

		# Need contact ID, so query that first
		contacts = self.get_contact_for_phone(contact_phone)
		if not contacts: raise Exception('No contact found for phone %s', contact_phone)
		contact_id = contacts['records'][0]['Id']

		mtm_date_s = mtm_date.strftime('%Y-%m-%dT%H:%M:%S.000+0000')
		
		headers = {'Authorization': 'Bearer ' + self.get_access_token(),
			'Content-Type': 'application/json'}
		r = requests.patch(self.rest_url + '/sobjects/Contact/' + contact_id, 
			headers=headers,
			json={'last_whatsapp_mtm__c': mtm_date_s})
		if r.status_code != requests.codes.ok:
			r.raise_for_status()

class OverAiRequest (object):
	def __init__(self, webhook_request):

		self.webhook_request = webhook_request
		self.caller_id = webhook_request['UserId']

	def get_parameter(self, parameter_name):
		try:
			params = self.webhook_request['Intent']['Parameters']
			p = next(x for x in params if x['Name'] == parameter_name)
			return p['Value']
		except (KeyError, StopIteration):
			return None

	def get_language(self):
		return self.webhook_request['Language']

	def get_intent_name(self):
		return self.webhook_request['Intent']['Name']

class SF_Order (Resource):

	def post(self):
		# pprint(vars(request))
		# print(request.json)

		timer_start = timer()

		req = OverAiRequest(request.get_json())

		con = SFConnection()
		timer_start_sf = timer()
		con.authenticate()
		timer_end_sf = timer()
		print('SF_Order.post SF uthentication took ', timer_end_sf-timer_start_sf, ' secs')

		caller_id = req.caller_id

		order_number = req.get_parameter('ORDER_NUMBER')

		app.logger.info('Received request for order number %s', order_number)

		timer_start_sf = timer()
		if order_number:
			last_order = con.get_order_by_number(caller_id, order_number)
		else:
			last_order = con.get_last_order_by_phone(caller_id)
		timer_end_sf = timer()
		print('SF_Order.post get order from SF took ', timer_end_sf-timer_start_sf, ' secs')

		# pprint(last_order)

		overai_response = dict()

		if last_order['totalSize'] > 0:
			last_order_record = last_order['records'][0]
			overai_response['ForceIntent'] = {'IntentName': 'order_status'}
			overai_response['SessionParameters'] = [
				{'Name': 'ORDER_NUMBER',
			 	'Type': '@sys.digits',
		     	'Value': last_order_record['Name']},
				{'Name': 'ORDER_DELIVERY_DATE',
		     	'Type': '@sys.date',
		     	'Value': last_order_record['Delivery_Date__c']},
				{'Name': 'ORDER_STATUS',
			 	'Type': '@sys.any',
			 	'Value': last_order_record['Status__c']},
				]

			# Update associated contact with order_number for potential later screen pops
			contact_id = last_order_record['Contact__r']['Id']
			timer_start_sf = timer()
			con.update_contact_for_order(contact_id, last_order_record['Name'])
			timer_end_sf = timer()
			print('SF_Order.post update_contact took ', timer_end_sf-timer_start_sf, ' secs')

			# pprint(overai_response)

			timer_end = timer()
			print('SF_Order.post took ', timer_end-timer_start, ' secs')

			return jsonify(overai_response)
		else:
			app.logger.warning('Could not find order for number %s', order_number)
			# caller_id = req.caller_id
			contact_response = con.get_contact_for_phone(caller_id)
			contact = contact_response['records'][0]
			con.update_contact_for_order(contact['Id'], '')
			overai_response['ForceIntent'] = {'IntentName': 'order_not_found'}
			# overai_response['Response'] = {'IntroSpeakOut': 'Sorry, I could not find that order. Please try again.'}
			# overai_response['SessionParameters'] = [
			# 	{'Name': 'ORDER_NUMBER',
			#	 'Value': '',
			# 	 'Type': '@sys.number'}
			# ]
			timer_end = timer()
			print('SF_Order.post took ', timer_end-timer_start, ' secs')
			return jsonify(overai_response)
		

class SF_Contact (Resource):
	def post(self):

		timer_start = timer()
		req = OverAiRequest(request.get_json())

		pprint(req)

		con = SFConnection()
		con.authenticate()

		caller_id = req.caller_id
		contact_response = con.get_contact_for_phone(caller_id)
		overai_response = {'Result': {}}

		if contact_response['totalSize'] == 0:
			overai_response['Result'] = {'IntroSpeakOut': 'No matching Salesforce record found'}
			overai_response['ForceIntent'] = {'IntentName': 'end_call'}
		else:
			contact = contact_response['records'][0]
			overai_response['SessionParameters'] = [
				{'Name': 'CONTACT_ID',
				 'Type': '@sys.any',
				 'Value': contact['Id']},
				{'Name': 'CONTACT_FIRST_NAME',
				 'Type': '@sys.any',
				 'Value': contact['FirstName']},
				{'Name': 'CONTACT_LAST_NAME',
				 'Type': '@sys.any',
				 'Value': contact['LastName']},
				{'Name': 'CONTACT_NAME',
				 'Type': '@sys.any',
				 'Value': contact['Name']},
				{'Name': 'CONTACT_WHATSAPP',
				 'Type': '@sys.phone-number',
				 'Value': contact['OtherPhone']},
				{'Name': 'CONTACT_OUTSTANDING_AMOUNT',
				 'Type': '@sys.number',
				 'Value': contact['Outstanding_Amount__c']},
				{'Name': 'CONTACT_CURRENCY',
				 'Type': '@sys.any',
				 'Value': contact['Currency_Text_To_Speech__c']}
			]
			print('Contact request for intent', req.get_intent_name())
			if req.get_intent_name() == 'order_help':
				if req.get_language() == 'de-DE':
					print('German Language detected')
					overai_response['Result'] = {
						'IntroSpeakOut': """Willkommen zurück %s. Geht es um ihre letzte Bestellung? Oder eine ältere Bestellung?""" % (contact['FirstName'], )
					}
				else:	
					print('Requested Language is ', req.get_language())
					overai_response['Result'] = {
						'IntroSpeakOut': """Welcome back %s. Is this about your most recent order? Or an earlier order?""" % (contact['FirstName'], )
					}
			elif req.get_intent_name() == 'billing':
				outstanding_amount = contact['Outstanding_Amount__c']
				print('Request for outstanding amount yielded %s' % outstanding_amount)
				if outstanding_amount > 0:
					overai_response['ForceIntent'] = {'IntentName': 'billing_confirm_payment'}
				else:
					overai_response['ForceIntent'] = {'IntentName': 'billing_confirm_route'}
			elif req.get_intent_name() == 'billing_route_call_pci':
				outstanding_amount = contact['Outstanding_Amount__c']
				print('Get Contact Info after PCI. Outstanding amount is %s' % outstanding_amount)
				if outstanding_amount > 0:
					overai_response['ForceIntent'] = {'IntentName': 'billing_payment_ok'}
				else:
					overai_response['ForceIntent'] = {'IntentName': 'billing_payment_not_ok'}


		# pprint(overai_response)

		timer_end = timer()
		print('SF_Contact.post took ', timer_end-timer_start, ' secs')

		return jsonify(overai_response)

class SF_AIContext (Resource):
	def post(self):
		timer_start = timer()
		req = OverAiRequest(request.get_json())

		pprint(req)

		ai_context = req.get_parameter('AI_CONTEXT')
		# app.logger.warning('SF_AIContext.post for %s with context %s' % (req.caller_id, ai_context))
		print('Setting context ', ai_context)

		# pprint(req)

		con = SFConnection()
		con.authenticate()

		contacts = con.get_contact_for_phone(req.caller_id)
		if not contacts: raise Exception('No contact found for phone %s', contact_phone)
		contact_id = contacts['records'][0]['Id']
		con.update_contact_for_ai_context(contact_id, ai_context)
		# Always route after updating the context. The context will be displayed in ContactPad

		timer_end = timer()
		print('SF_AIContext.post took ', timer_end-timer_start, ' secs')
		return jsonify({'ForceIntent': {'IntentName': 'route_call'}})

application = app = Flask(__name__)
api = Api(app)
api.add_resource(SF_Order, '/orderstatus')
api.add_resource(SF_Contact, '/contact')
api.add_resource(NexmoWhatsAppSendMessageOrder, '/sendwhatsapp/order')
api.add_resource(NexmoWhatsAppSendMessageProduct, '/sendwhatsapp/product')
api.add_resource(NexmoWhatsAppReceiveMessage, '/receivewhatsappmessage')
api.add_resource(NexmoWhatsAppReceiveStatus, '/receivewhatsappstatus')
api.add_resource(SF_AIContext, '/updatecontext')
@app.route('/')
def index():
	return 'OK', 200

def main():
	con = SFConnection()
	con.authenticate()
	# con.update_whatsapp_mtm_date('491636115432', datetime.utcnow())

	# print('token ' + con.get_access_token() + "\n")

	r = con.get_contact_for_phone('491636115432')

	pprint(r)
	# pprint(vars(r))
	

if __name__ == '__main__':
	# port = int(os.environ.get('PORT', 5000))
	app.run(host='0.0.0.0', port=5050)

	# main()


