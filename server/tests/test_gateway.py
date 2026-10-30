from io import BytesIO
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from fastapi import HTTPException
from server import gateway


class GatewayTests(unittest.TestCase):
    def test_missing_credentials_do_not_attempt_network(self):
        with patch.dict(os.environ, {}, clear=True), patch('server.gateway.urlopen') as request:
            with self.assertRaises(HTTPException) as error:
                gateway.embed_texts(['hello'], model='test')
            self.assertEqual(error.exception.status_code, 503)
            request.assert_not_called()

    def test_cloud_embeddings_restore_input_order_without_local_prefixes(self):
        def response(request, **kwargs):
            body = json.loads(request.data)
            self.assertEqual(body['input'], ['first', 'second'])
            self.assertEqual(request.full_url, 'https://ai-gateway.vercel.sh/v1/embeddings')
            return BytesIO(json.dumps({'data': [
                {'index': 1, 'embedding': [2, 1]}, {'index': 0, 'embedding': [1, 1]}
            ]}).encode())
        with patch.dict(os.environ, {'AI_GATEWAY_API_KEY': 'test-key'}), patch('server.gateway.urlopen', side_effect=response):
            self.assertEqual(gateway.embed_texts(['first', 'second'], model='test'), [[1, 1], [2, 1]])

    def test_invalid_vectors_and_duplicate_indexes_are_rejected(self):
        for data in ([{'index': 0, 'embedding': [0, 0]}],
                     [{'index': 0, 'embedding': [True, 1]}],
                     [{'index': 1, 'embedding': [1, 1]}]):
            with patch('server.gateway.request_json', return_value={'data': data}):
                with self.assertRaises(HTTPException):
                    gateway.embed_texts(['hello'], model='test')

    def test_authentication_errors_never_expose_response_secrets(self):
        error = HTTPError('https://ai-gateway.vercel.sh/v1/embeddings', 401, 'private-detail', {}, None)
        with patch.dict(os.environ, {'AI_GATEWAY_API_KEY': 'test-key'}), patch('server.gateway.urlopen', side_effect=error):
            with self.assertRaises(HTTPException) as caught:
                gateway.embed_texts(['hello'], model='test')
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn('private-detail', caught.exception.detail)

    def test_chat_uses_cloud_response_format(self):
        with patch('server.gateway.request_json', return_value={'choices': [{'message': {'content': 'Answer [1]'}}]}) as request:
            self.assertEqual(gateway.generate_chat([{'role': 'user', 'content': 'Question'}], 'test'), 'Answer [1]')
        self.assertEqual(request.call_args.args[0], 'chat/completions')

    def test_billing_verification_error_is_actionable(self):
        body = BytesIO(b'{"error":{"type":"customer_verification_required"}}')
        error = HTTPError('https://ai-gateway.vercel.sh/v1/embeddings', 403, '', {}, body)
        with patch.dict(os.environ, {'AI_GATEWAY_API_KEY': 'test-key'}), patch('server.gateway.urlopen', side_effect=error):
            with self.assertRaises(HTTPException) as caught:
                gateway.embed_texts(['hello'], model='test')
        self.assertIn('billing verification', caught.exception.detail)
