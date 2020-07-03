import eth_abi
import json
import os
import re
import sys
import urllib.request
from web3.auto import w3

keccak256 = w3.soliditySha3

root         = '/'
inputDir     = '{}iexec_in/'.format(root)
outputDir    = '{}scone/iexec_out'.format(root)
callbackFile = 'callback.iexec'
completedComputeFile = 'completed-compute.iexec'

iexec_out = os.environ['IEXEC_OUT']
iexec_in = os.environ['IEXEC_IN']
dataset_filepath = iexec_in + '/' + os.environ['IEXEC_DATASET_FILENAME']

class Lib:
	def parseValue(rawValue, ethType, power):
		if re.search('^u?int[0-9]*$', ethType):
			return round(float(rawValue) * 10 ** int(power))
		else:
			return rawValue

	def formatArgs(args):
		return '&'.join('{}={}'.format(k,v) for k,v in args.items())

	def getAPIKey():
		# Dataset file is a zip that is extracted before the entrypoint. read the key.txt file extracted from it
		try:
			with open(dataset_filepath, 'r') as file:
				apiKey = file.read().strip()
				if not re.search('^[0-9a-zA-Z]{1,128}$', apiKey):
					raise Exception('Invalid API key')
				return apiKey
		except FileNotFoundError:
			raise Exception('Missing API key dataset')

	def fetchMarketData(region, endpoint, params):
		print('Request https://{region}.market-api.kaiko.io/v1/data/trades.v1/{endpoint}?{params}'.format(
			region   = region,
			endpoint = endpoint,
			params   = params,
		))
		return json.loads(
			urllib.request.urlopen(
				urllib.request.Request(
					'https://{region}.market-api.kaiko.io/v1/data/trades.v1/{endpoint}?{params}'.format(
						region   = region,
						endpoint = endpoint,
						params   = params,
					),
					headers = {
						'X-Api-Key': Lib.getAPIKey(),
						'User-Agent': 'Kaiko iExec Adapter',
					}
				)
			).read()
		)

class PriceFeed:
	def fetchRate(baseAsset, quoteAsset):
		return Lib.fetchMarketData(
			'us',
			'spot_direct_exchange_rate/{baseAsset}/{quoteAsset}/recent'.format(baseAsset=baseAsset, quoteAsset=quoteAsset),
			Lib.formatArgs({
				'interval': '1m',
				'limit':    720,
			})
		)

	def run(baseAsset, quoteAsset, power):
		response = PriceFeed.fetchRate(
			baseAsset  = baseAsset,
			quoteAsset = quoteAsset,
		)
		try:
			data      = response.get('data')[0]
			timestamp = data.get('timestamp')
			details   = 'Price-{base}/{quote}-{power}'.format(base=baseAsset.upper(), quote=quoteAsset.upper(), power=power)
			rawValue  = data.get('price')
			value     = Lib.parseValue(rawValue, 'uint256', power)
			return (timestamp, details, value)
		except Exception as e:
			raise Exception('API response parsing failure: {}'.format(e))


# Example usage:
# btc usd 9
if __name__ == '__main__':
	print('PriceFeed started')
	try:
		# EXECUTE CALL
		data = PriceFeed.run(
			baseAsset  = sys.argv[1],
			quoteAsset = sys.argv[2],
			power      = sys.argv[3],
		)
		print('- Success: {} {} {}'.format(*data))

		# GENERATE CALLBACK
		callback_data = eth_abi.encode_abi(['uint256', 'string', 'uint256'], [*data]).hex()
		callback_data = '0x{}'.format(callback_data)
		print('Offchain computing for Smart-Contracts [data:{}, callback_data:{}]'.format(data, callback_data))

		with open(iexec_out + '/computed.json', 'w+') as f:
			json.dump({ "callback-data" : callback_data}, f)


	except IndexError as e:
		print('Error: missing arguments')

	except Exception as e:
		print('Execution Failure: {}'.format(e))

	print('PriceFeed completed')
