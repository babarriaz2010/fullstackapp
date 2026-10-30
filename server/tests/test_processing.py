from io import BytesIO
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from server.local_embeddings import embed_texts

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from server.processing import (
    CHUNK_OVERLAP, CHUNK_SIZE, EMBEDDING_BATCH_SIZE, MAX_TEXT_CHARS,
    ProcessingError, extract_pages, prepare_document, split_pages,
)


def make_text_pdf(texts: list[str]) -> bytes:
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject('/Resources')] = DictionaryObject({
            NameObject('/Font'): DictionaryObject({
                NameObject('/F1'): DictionaryObject({
                    NameObject('/Type'): NameObject('/Font'),
                    NameObject('/Subtype'): NameObject('/Type1'),
                    NameObject('/BaseFont'): NameObject('/Helvetica'),
                })
            })
        })
        stream = DecodedStreamObject()
        escaped = text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        stream.set_data(f'BT /F1 12 Tf 72 700 Td ({escaped}) Tj ET'.encode('ascii'))
        page[NameObject('/Contents')] = writer._add_object(stream)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class ProcessingTests(unittest.TestCase):
    def test_text_decodes_bom_and_normalizes_newlines(self):
        self.assertEqual(extract_pages('notes.txt', b'\xef\xbb\xbfHello\r\nWorld'), [(None, 'Hello\nWorld')])

    def test_real_pdf_text_and_page_numbers_are_preserved(self):
        pages = extract_pages('notes.pdf', make_text_pdf(['First page text.', 'Second page text.']))
        chunks = split_pages(pages)
        self.assertEqual([chunk.page_number for chunk in chunks], [1, 2])
        self.assertIn('First page text.', chunks[0].content)
        self.assertIn('Second page text.', chunks[1].content)

    def test_empty_text_and_image_only_pdf_do_not_get_fake_chunks(self):
        for pages in ([(None, ' \n\t')], extract_pages('blank.pdf', make_text_pdf(['']))):
            with self.assertRaises(ProcessingError):
                split_pages(pages)

    def test_chunk_overlap_covers_long_text_without_losing_tail(self):
        text = 'x' * (CHUNK_SIZE * 3 + 83)
        chunks = split_pages([(None, text)])
        self.assertEqual(chunks[0].start_char, 0)
        self.assertEqual(chunks[-1].end_char, len(text))
        for first, second in zip(chunks, chunks[1:]):
            self.assertEqual(first.end_char - second.start_char, CHUNK_OVERLAP)
        self.assertTrue(all(len(chunk.content) <= CHUNK_SIZE for chunk in chunks))

    def test_excessive_text_is_rejected_before_model_call(self):
        with patch('server.processing.embed_texts') as embed:
            with self.assertRaises(ProcessingError):
                prepare_document('notes.txt', b'x' * (MAX_TEXT_CHARS + 1))
            embed.assert_not_called()

    def test_embeddings_match_input_order_across_batches(self):
        def response_for(request, **_kwargs):
            payload = json.loads(request.data)
            self.assertFalse(payload['truncate'])
            vectors = [[float(text.split(': ')[1]) + 1, 1.0] for text in payload['input']]
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps({'embeddings': vectors}).encode()
            return response
        texts = [str(index) for index in range(EMBEDDING_BATCH_SIZE + 3)]
        with patch('server.local_embeddings.urlopen', side_effect=response_for):
            vectors = embed_texts(texts, model='nomic-embed-text:latest')
        self.assertEqual([vector[0] for vector in vectors], list(range(1, len(texts) + 1)))

    def test_invalid_ollama_vectors_are_rejected(self):
        for embeddings in ([], [[1, float('nan')]], [[0, 0]], [[True, 1]], [[1], [1, 2]]):
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps({'embeddings': embeddings}).encode()
            with patch('server.local_embeddings.urlopen', return_value=response):
                with self.assertRaises(ProcessingError):
                    embed_texts(['one'] * max(1, len(embeddings)), model='nomic-embed-text:latest')

    def test_ollama_connection_error_is_actionable_and_sanitized(self):
        with patch('server.local_embeddings.urlopen', side_effect=URLError('private-host-details')):
            with self.assertRaises(ProcessingError) as error:
                embed_texts(['hello'], model='nomic-embed-text:latest')
        self.assertEqual(error.exception.status_code, 503)
        self.assertNotIn('private-host-details', str(error.exception))


if __name__ == '__main__':
    unittest.main()
